# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Dumpers for OAI harvested records."""

from __future__ import annotations

from typing import Any, override

from invenio_records.dumpers.search import SearchDumperExt


class AddHarvesterDumperExt(SearchDumperExt):
    """Base class for OAI record dumpers."""

    @override
    def dump(self, record: Any, data: dict[str, Any]) -> None:
        """Dump the data."""
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
