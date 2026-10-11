# SPDX-FileCopyrightText: 2023-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Proxies for OAI-PMH Harvester extension."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import current_app
from werkzeug.local import LocalProxy

if TYPE_CHECKING:
    from .ext import OARepoOAIHarvesterExt
    from .oai_harvester.service import OAIHarvesterService
    from .oai_record.service import OAIRecordService

    current_harvester: OARepoOAIHarvesterExt
    current_oai_record_service: OAIRecordService
    current_oai_harvester_service: OAIHarvesterService

current_harvester = LocalProxy(  # type: ignore[assignment]
    lambda: current_app.extensions["oarepo_oaipmh_harvester"]
)

current_oai_record_service = LocalProxy(  # type: ignore[assignment]
    lambda: current_harvester.oai_record_service
)

current_oai_harvester_service = LocalProxy(  # type: ignore[assignment]
    lambda: current_harvester.oai_harvester_service
)
