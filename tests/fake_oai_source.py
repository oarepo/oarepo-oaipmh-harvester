# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""An in-process OAI-PMH source for the tests.

The `source` fixture (conftest) serves a `FakeOAIPMHSource` through `httpx.MockTransport`, so
the harvester's requests go through the real `httpx` client of oaipmh-scythe and the source
parses the real query string. It answers `Identify`, `ListIdentifiers`, `ListRecords` and
`GetRecord` like a real source:

* records are filtered by `from` / `until` (inclusive; a date-only bound covers the whole day),
* listings are paged with resumption tokens (`page_size`); the first page of a listing reports
  `completeListSize` unless `complete_list_size` is off,
* arguments are validated - a datestamp finer than the `granularity` of the source, `from`
  after `until`, an unknown metadata prefix and unknown arguments are OAI-PMH errors,
* deleted records are reported with `status="deleted"`.

Records are changed between harvests with `add`, `update` and `delete`; `on(verb, callback)`
calls `callback(params)` on a request - to simulate an outage (raise) or something happening
during a harvest (a user stopping the run, records moving to a newer datestamp).
"""

from __future__ import annotations

import datetime as dt
import itertools
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

OAI_NAMESPACE = "http://www.openarchives.org/OAI/2.0/"
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
OAI_DC_NAMESPACE = "http://www.openarchives.org/OAI/2.0/oai_dc/"

SECONDS_GRANULARITY = "YYYY-MM-DDThh:mm:ssZ"
DAY_GRANULARITY = "YYYY-MM-DD"

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SECONDS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_ARGUMENTS = {
    "Identify": set(),
    "ListIdentifiers": {"metadataPrefix", "from", "until", "set"},
    "ListRecords": {"metadataPrefix", "from", "until", "set"},
    "GetRecord": {"identifier", "metadataPrefix"},
}


def timestamp(value: str) -> dt.datetime:
    """Parse a datestamp of either granularity into an aware UTC datetime."""
    parsed = dt.datetime.fromisoformat(value)
    return parsed.replace(tzinfo=dt.UTC) if parsed.tzinfo is None else parsed.astimezone(dt.UTC)


def datestamps(count: int = 8, *, days: int = 400) -> list[str]:
    """`count` datestamps spread evenly over the last `days` days."""
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    step = dt.timedelta(days=days) / count
    return [(now - dt.timedelta(days=days) + step * index).strftime("%Y-%m-%dT%H:%M:%SZ") for index in range(count)]


def assert_windows_cover(windows: Iterable, source: FakeOAIPMHSource) -> None:
    """Assert the windows (with `start` / `end`) do not overlap and every record falls in exactly one."""
    windows = sorted(windows, key=lambda window: window.start)
    for previous, current in itertools.pairwise(windows):
        assert current.start > previous.end
    for record in source.records:
        value = timestamp(record.datestamp)
        assert len([window for window in windows if window.start <= value <= window.end]) == 1


class OAIError(Exception):
    """An OAI-PMH error answered to the harvester."""

    def __init__(self, code: str, message: str = ""):
        """Remember the OAI-PMH error code."""
        super().__init__(message or code)
        self.code = code


@dataclass
class Record:
    """A record of the source."""

    identifier: str
    datestamp: str
    titles: list[str]
    deleted: bool = False


class FakeOAIPMHSource:
    """OAI-PMH source with records the test sets up, filtered and paged as by a real source."""

    def __init__(
        self,
        stamps: Iterable[str] = (),
        *,
        granularity: str = SECONDS_GRANULARITY,
        complete_list_size: bool = True,
        page_size: int = 100,
    ):
        """Add a record for every datestamp; see the module docstring for the options."""
        self.records: list[Record] = []
        self.granularity = granularity
        self.complete_list_size = complete_list_size
        self.page_size = page_size
        self.requests: list[dict[str, str]] = []
        self._hooks: dict[str, list[Callable[[dict[str, str]], None]]] = {}
        self.extend(stamps)

    # --- records -------------------------------------------------------------------------

    def add(self, datestamp: str, *, identifier: str | None = None, title: str | list[str] | None = None) -> str:
        """Add a record; `title` defaults to the identifier, a list of titles is not importable."""
        identifier = identifier or f"oai:test:{len(self.records)}"
        titles = title if isinstance(title, list) else [title or identifier]
        self.records.append(Record(identifier, datestamp, titles))
        return identifier

    def extend(self, stamps: Iterable[str]) -> list[str]:
        """Add a record for every datestamp."""
        return [self.add(stamp) for stamp in stamps]

    def update(self, identifier: str, datestamp: str, *, title: str | None = None) -> None:
        """Change a record - it gets a newer datestamp and optionally a new title."""
        record = self._record(identifier)
        record.datestamp = datestamp
        if title is not None:
            record.titles = [title]

    def delete(self, identifier: str, datestamp: str) -> None:
        """Delete a record - the source keeps it as a deleted record."""
        record = self._record(identifier)
        record.datestamp = datestamp
        record.deleted = True

    @property
    def identifiers(self) -> set[str]:
        """Identifiers of the records that are not deleted."""
        return {record.identifier for record in self.records if not record.deleted}

    def on(self, verb: str, callback: Callable[[dict[str, str]], None]) -> None:
        """Call `callback(params)` on every request with the verb, before it is answered."""
        self._hooks.setdefault(verb, []).append(callback)

    # --- protocol ------------------------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Answer an HTTP request of the harvester (the handler of `httpx.MockTransport`)."""
        params = dict(request.url.params) if request.method == "GET" else dict(httpx.QueryParams(request.content))
        self.requests.append(params)
        try:
            body = self._answer(params)
        except OAIError as e:
            body = f'<error code="{e.code}">{escape(str(e))}</error>'
        content = (
            "<?xml version='1.0' encoding='UTF-8'?>"
            f'<OAI-PMH xmlns="{OAI_NAMESPACE}"><responseDate>2026-01-01T00:00:00Z</responseDate>{body}</OAI-PMH>'
        )
        return httpx.Response(200, content=content.encode(), headers={"Content-Type": "text/xml; charset=utf-8"})

    def _answer(self, params: dict[str, str]) -> str:
        verb = params.get("verb", "")
        if verb not in _ARGUMENTS:
            raise OAIError("badVerb")
        if "resumptionToken" in params:
            params = self._resume(verb, params)
        else:
            self._validate(verb, params)
        for hook in self._hooks.get(verb, []):
            hook(params)
        if verb == "Identify":
            return self._identify()
        if verb == "GetRecord":
            return f"<GetRecord>{self._record_xml(self._record(params['identifier']))}</GetRecord>"
        selected = [record for record in self.records if self.in_range(record.datestamp, params)]
        if not selected:
            raise OAIError("noRecordsMatch")
        offset = int(params.get("offset", 0))
        page = selected[offset : offset + self.page_size]
        items = "".join(
            self._header_xml(record) if verb == "ListIdentifiers" else self._record_xml(record) for record in page
        )
        return f"<{verb}>{items}{self._token(verb, params, offset, len(page), len(selected))}</{verb}>"

    def _validate(self, verb: str, params: dict[str, str]) -> None:
        unknown = set(params) - _ARGUMENTS[verb] - {"verb"}
        if unknown:
            raise OAIError("badArgument", f"unknown arguments {sorted(unknown)}")
        if verb == "Identify":
            return
        if params.get("metadataPrefix") != "oai_dc":
            raise OAIError("cannotDisseminateFormat")
        bounds = [params[key] for key in ("from", "until") if key in params]
        for value in bounds:
            # every source accepts days, only a seconds-granularity source accepts times
            if not (_DAY.match(value) or (self.granularity == SECONDS_GRANULARITY and _SECONDS.match(value))):
                raise OAIError("badArgument", f"datestamp {value} does not match the granularity {self.granularity}")
        if len(bounds) == 2 and (len(bounds[0]) != len(bounds[1]) or timestamp(bounds[0]) > timestamp(bounds[1])):
            raise OAIError("badArgument", "from and until differ in granularity or from is after until")

    @staticmethod
    def _resume(verb: str, params: dict[str, str]) -> dict[str, str]:
        if set(params) != {"verb", "resumptionToken"}:
            raise OAIError("badArgument", "resumptionToken is exclusive")
        resumed = dict(httpx.QueryParams(params["resumptionToken"]))
        if resumed.get("verb") != verb:
            raise OAIError("badResumptionToken")
        return resumed

    def _token(self, verb: str, params: dict[str, str], offset: int, count: int, total: int) -> str:
        """Resumption token after a page - empty on the last page of a paged listing."""
        size = f' completeListSize="{total}"' if self.complete_list_size else ""
        if offset + count >= total:
            return f"<resumptionToken{size}/>" if offset else ""
        token = str(httpx.QueryParams({**params, "verb": verb, "offset": offset + count}))
        return f"<resumptionToken{size}>{escape(token)}</resumptionToken>"

    def in_range(self, datestamp: str, params: dict[str, str]) -> bool:
        """Whether a record with the datestamp is selected by the `from` / `until` of the request."""
        value = timestamp(datestamp)
        start, end = params.get("from"), params.get("until")
        if start and (value.date() < timestamp(start).date() if _DAY.match(start) else value < timestamp(start)):
            return False
        return not end or (value.date() <= timestamp(end).date() if _DAY.match(end) else value <= timestamp(end))

    def _record(self, identifier: str) -> Record:
        for record in self.records:
            if record.identifier == identifier:
                return record
        raise OAIError("idDoesNotExist")

    # --- xml -----------------------------------------------------------------------------

    def _identify(self) -> str:
        earliest = min((record.datestamp for record in self.records), default="1970-01-01T00:00:00Z")
        return (
            "<Identify><repositoryName>Test</repositoryName><baseURL>https://example.org/oai</baseURL>"
            "<protocolVersion>2.0</protocolVersion><adminEmail>a@example.org</adminEmail>"
            f"<earliestDatestamp>{earliest}</earliestDatestamp>"
            f"<deletedRecord>persistent</deletedRecord><granularity>{self.granularity}</granularity></Identify>"
        )

    @staticmethod
    def _header_xml(record: Record) -> str:
        status = ' status="deleted"' if record.deleted else ""
        return (
            f"<header{status}><identifier>{escape(record.identifier)}</identifier>"
            f"<datestamp>{record.datestamp}</datestamp></header>"
        )

    def _record_xml(self, record: Record) -> str:
        if record.deleted:
            return f"<record>{self._header_xml(record)}</record>"
        titles = "".join(f"<dc:title>{escape(title)}</dc:title>" for title in record.titles)
        return (
            f"<record>{self._header_xml(record)}<metadata>"
            f'<oai_dc:dc xmlns:dc="{DC_NAMESPACE}" xmlns:oai_dc="{OAI_DC_NAMESPACE}">{titles}</oai_dc:dc>'
            "</metadata></record>"
        )
