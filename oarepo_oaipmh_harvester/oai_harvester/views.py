#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""API views for OAI harvester."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Blueprint, Flask


def create_api_blueprint(app: Flask) -> Blueprint:
    """Create OAIHarvester blueprint."""
    return app.extensions["oarepo_oaipmh_harvester"].oai_harvester_resource.as_blueprint()
