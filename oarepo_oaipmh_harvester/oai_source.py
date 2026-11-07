# SPDX-FileCopyrightText: 2024-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Talking to an OAI-PMH source - `Identify`, datestamps and record counts.

OAI-PMH sources differ in the granularity of their datestamps (`YYYY-MM-DD` or
`YYYY-MM-DDThh:mm:ssZ`, advertised by `Identify`) and in whether they report how many records
a request matches (`completeListSize` of a resumption token). A source that only supports
dates rejects a time component, and a source that does not report the size can not be split
by count - both matter when a harvest is split into windows.

[format_oaipmh_datestamp][oarepo_oaipmh_harvester.oai_source.format_oaipmh_datestamp]
formats a datetime for a source by its `base_url`, tolerating a source that does not answer
`Identify`. [OAIPMHSource][oarepo_oaipmh_harvester.oai_source.OAIPMHSource] wraps the two
requests a harvest needs beyond the records themselves - `Identify` (cached, for the
granularity and the `earliestDatestamp`) and a `ListIdentifiers` count of a range.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from flask import current_app

SECONDS_GRANULARITY = "YYYY-MM-DDThh:mm:ssZ"
"""The `granularity` of a source whose datestamps contain a time."""


def parse_datestamp(value: str) -> datetime:
    """Parse an OAI-PMH datestamp; a value without a timezone is taken as UTC."""
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def floor_to(value: datetime, unit: timedelta) -> datetime:
    """Truncate a datetime to the granularity of `unit` (one second or one day)."""
    if unit < timedelta(days=1):
        return value.replace(microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def format_datestamp(value: datetime, *, seconds: bool) -> str:
    """Format a datetime as an OAI-PMH datestamp of the given granularity."""
    return value.strftime("%Y-%m-%dT%H:%M:%SZ") if seconds else value.strftime("%Y-%m-%d")


@lru_cache(maxsize=32)
def _granularity(base_url: str) -> str | None:
    """Return the granularity advertised by the OAI-PMH Identify verb (cached).

    Returns None if the probe fails - callers should fall back to the most
    restrictive date-only format, which is legal under both granularities.
    Note: results are cached for the process lifetime, so a granularity change
    on the server side requires a worker restart to take effect.
    """
    try:
        return OAIPMHSource(base_url).granularity
    except Exception:
        current_app.logger.warning(
            "Could not probe Identify granularity of %s, assuming date-only", base_url, exc_info=True
        )
        return None


def format_oaipmh_datestamp(since: datetime | str, base_url: str) -> str:
    """Format `since` as an OAI-PMH datestamp matching the server granularity.

    OAI-PMH repositories that advertise `YYYY-MM-DD` granularity (e.g. the
    ASEP ARL server) reject any time component, while `...+00:00` offsets
    produced by `datetime.isoformat()` are illegal in both granularities.
    Seconds-granularity servers get `YYYY-MM-DDThh:mm:ssZ` (UTC), others a
    bare `YYYY-MM-DD`.
    """
    if isinstance(since, str):
        import arrow

        since_dt = arrow.get(since).datetime
    else:
        since_dt = since

    if since_dt.utcoffset() is None:
        since_dt = since_dt.astimezone()  # interpret naive input as local time
    since_dt = since_dt.astimezone(UTC)
    return format_datestamp(since_dt, seconds=_granularity(base_url) == SECONDS_GRANULARITY)


class OAIPMHSource:
    """An OAI-PMH endpoint, as a harvest and its planning need it.

    `Identify` and its attributes are requested lazily and cached, so one instance should be
    used for one harvest (or one planning run).
    """

    def __init__(self, base_url: str, *, metadata_prefix: str | None = None, set_: str | None = None):
        """Remember the endpoint and the selection; no request is made here."""
        self.base_url = base_url
        self.metadata_prefix = metadata_prefix
        self.set_ = set_
        self.probes = 0
        """Number of `ListIdentifiers` counting requests made so far."""
        self._scythe: Any = None
        self._identify: Any = None

    @property
    def scythe(self) -> Any:
        """Client of the endpoint."""
        if self._scythe is None:
            from oaipmh_scythe import Scythe

            self._scythe = Scythe(self.base_url)
        return self._scythe

    @property
    def identify(self) -> Any:
        """The `Identify` response (cached)."""
        if self._identify is None:
            self._identify = self.scythe.identify()
        return self._identify

    @property
    def granularity(self) -> str | None:
        """The `granularity` the source advertises."""
        return getattr(self.identify, "granularity", None)

    @property
    def seconds(self) -> bool:
        """Whether the datestamps of the source contain a time."""
        return self.granularity == SECONDS_GRANULARITY

    @property
    def unit(self) -> timedelta:
        """Smallest step of the source's datestamps - one second or one day."""
        return timedelta(seconds=1) if self.seconds else timedelta(days=1)

    @property
    def earliest(self) -> datetime:
        """`earliestDatestamp` of the source, floored to its granularity."""
        return floor_to(parse_datestamp(self.identify.earliestDatestamp), self.unit)

    def format(self, value: datetime) -> str:
        """Format a datetime as a datestamp the source accepts."""
        return format_datestamp(value, seconds=self.seconds)

    def count(self, start: datetime | str | None = None, end: datetime | str | None = None) -> int | None:
        """Return the number of records in the range, `None` if the source does not tell.

        The bounds may be datetimes (formatted for the source) or datestamps the source
        accepts already - the reader config of a harvest holds the latter. The first page of
        `ListIdentifiers` is enough - either the `completeListSize` of its resumption token
        says how many records match, or the whole answer fitted on that page. A range with no
        records (`noRecordsMatch`) has 0.
        """
        from oaipmh_scythe.exceptions import NoRecordsMatch
        from oaipmh_scythe.iterator import OAIItemIterator

        self.probes += 1
        query = {"verb": "ListIdentifiers", "metadataPrefix": self.metadata_prefix or "oai_dc"}
        if start is not None:
            query["from"] = start if isinstance(start, str) else self.format(start)
        if end is not None:
            query["until"] = end if isinstance(end, str) else self.format(end)
        if self.set_:
            query["set"] = self.set_
        try:
            iterator = OAIItemIterator(self.scythe, query)
        except NoRecordsMatch:
            return 0
        token = iterator.resumption_token
        if token is not None and token.complete_list_size:
            return int(token.complete_list_size)
        response = iterator.oai_response
        if response is None:  # the iterator always fetches the first page in its constructor
            return None
        if token is None or not token.token:  # everything fitted on the first page
            return len(response.xml.findall(f".//{self.scythe.oai_namespace}header"))
        return None
