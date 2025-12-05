#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
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
