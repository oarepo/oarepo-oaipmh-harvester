# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Celery tasks for OAI harvester."""

from __future__ import annotations

import datetime as dt

from celery import shared_task
from invenio_db import db

from ..proxies import current_oai_harvester_service
from .models import OAIHarvester


@shared_task
def index_oai_harvesters() -> None:
    """Reindex OAI harvesters."""
    oai_harvesters = (
        db.session.query(OAIHarvester.id)
        .filter(OAIHarvester.last_update_time > dt.datetime.now(dt.UTC) - dt.timedelta(days=1))
        .yield_per(1000)
    )

    current_oai_harvester_service.indexer.bulk_index([u.id for u in oai_harvesters])
