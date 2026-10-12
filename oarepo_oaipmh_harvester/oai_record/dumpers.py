# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Dumpers for OAI harvested records."""

from __future__ import annotations

from typing import Any, override

from invenio_records.dumpers.search import SearchDumperExt

MAX_KEYWORD_LENGTH = 512
"""`ignore_above` of the `errors.*` keyword fields - longer values are not indexed."""


class AddHarvesterDumperExt(SearchDumperExt):
    """Dumper extension adding the harvester's name and managers to the search document."""

    @override
    def dump(self, record: Any, data: dict[str, Any]) -> None:
        """Add the harvester name and managers to the dumped data."""
        harvester = record.harvester
        data["harvester_name"] = harvester.name
        data["harvest_managers"] = harvester.harvest_managers or []

    @override
    def load(self, data: dict[str, Any], record_cls: type) -> None:
        """Load the data.

        Reverse the changes made by the dump method.
        """
        data.pop("harvester_name", None)
        data.pop("harvest_managers", None)


def _keyword(value: str | None) -> str | None:
    """Collapse whitespace and truncate the value so that it is indexed (and faceted)."""
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text if len(text) <= MAX_KEYWORD_LENGTH else text[: MAX_KEYWORD_LENGTH - 1] + "…"


def _innermost_frame(location: str | None) -> str | None:
    """Return the innermost frame of a stored traceback, other locations as they are.

    Tracebacks are stored as `function@file:line` lines, each followed by indented lines
    with the frame's local variables; the innermost frame is where the exception was raised.
    """
    if not location or "\n" not in location:
        return location
    frames = [line for line in location.splitlines() if line and not line.startswith(" ")]
    return frames[-1] if frames else location


class ErrorsFacetDumperExt(SearchDumperExt):
    """Make the errors of the search document usable in facets.

    The `errors.*` fields are keywords with `ignore_above: 512` - a longer message or a
    traceback in `location` would not be indexed at all, so the record would be missing in
    the error facets. The search document gets single-line messages truncated to fit, the
    innermost traceback frame as the location and a placeholder for an empty message;
    the database keeps the full errors (shown in the harvest record detail).
    """

    @override
    def dump(self, record: Any, data: dict[str, Any]) -> None:
        """Shorten the errors of the search document."""
        data["errors"] = [
            {
                **error,
                "type": _keyword(error.get("type")),
                "message": _keyword(error.get("message") or f"{error.get('type') or 'Error'} (no message)"),
                "location": _keyword(_innermost_frame(error.get("location"))),
            }
            for error in data.get("errors") or []
        ]

    @override
    def load(self, data: dict[str, Any], record_cls: type) -> None:
        """Keep the shortened errors - the full ones are only in the database."""
