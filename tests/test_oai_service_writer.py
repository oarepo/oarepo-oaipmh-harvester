#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from invenio_vocabularies.datastreams.datastreams import StreamEntry

from oarepo_oaipmh_harvester.oai_record.models import OAIHarvestedRecord
from oarepo_oaipmh_harvester.writers.oai_service import OAIServiceWriter


def _entry(datestamp: dt.datetime, *, deleted: bool) -> StreamEntry:
    header = SimpleNamespace(identifier="oai:test:1", datestamp=datestamp, deleted=deleted)
    return StreamEntry(
        {
            "oai_record": SimpleNamespace(header=header, raw="<record/>"),
            "record": {"metadata": {"title": {"value": "Record 1"}}, "files": {"enabled": False}},
        }
    )


def test_existing_oai_record_gets_new_datestamp_and_deleted(app, db, search_clear, test_model, location, harvester):
    writer = OAIServiceWriter("test", publish=False, harvester_id=harvester)
    first = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    second = dt.datetime(2025, 2, 1, tzinfo=dt.UTC)

    writer.write(_entry(first, deleted=False))
    writer.write(_entry(second, deleted=True))

    oai_record = db.session.query(OAIHarvestedRecord).filter_by(oai_identifier="oai:test:1").one()
    assert oai_record.datestamp.replace(tzinfo=dt.UTC) == second
    assert oai_record.deleted is True
    assert oai_record.has_errors is False
