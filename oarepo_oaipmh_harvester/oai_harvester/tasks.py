#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Celery tasks for OAI harvester."""

from __future__ import annotations

import datetime

from celery import shared_task
from invenio_db import db

from ..proxies import current_oai_harvester_service
from .models import OAIHarvester


@shared_task
def index_oai_harvesters() -> None:
    """Reindex OAI harvesters."""
    oai_harvesters = (
        db.session.query(OAIHarvester.id)
        .filter(OAIHarvester.last_update_time > datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1))
        .yield_per(1000)
    )

    current_oai_harvester_service.indexer.bulk_index([u.id for u in oai_harvesters])
