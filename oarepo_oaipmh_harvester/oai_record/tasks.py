#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Reindexing task for OAI-PMH harvested records."""

from __future__ import annotations

import datetime

from celery import shared_task
from invenio_db import db

from ..proxies import current_oai_record_service
from .models import OAIHarvestedRecord


@shared_task
def index_oai_records() -> None:
    """Reindex OAI data."""
    oai_records = (
        db.session.query(OAIHarvestedRecord.id)
        .filter(OAIHarvestedRecord.last_update_time > datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1))
        .yield_per(1000)
    )

    current_oai_record_service.indexer.bulk_index([u.id for u in oai_records])
