#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
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
