# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""API views for OAI harvester."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Blueprint, Flask


def create_api_blueprint(app: Flask) -> Blueprint:
    """Create OAIHarvester blueprint."""
    return app.extensions["oarepo_oaipmh_harvester"].oai_harvester_resource.as_blueprint()
