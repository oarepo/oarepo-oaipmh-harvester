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

from invenio_access.permissions import system_identity
from invenio_vocabularies.datastreams.datastreams import StreamEntry
from oarepo_runtime import current_runtime

from oarepo_oaipmh_harvester.oai_record.models import OAIHarvestedRecord
from oarepo_oaipmh_harvester.writers.oai_service import LocalRecord, LocalState, OAIServiceWriter


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


def test_resolve_local_record(app, db, search_clear, test_model, location):
    service = current_runtime.models["test"].service

    def resolve(pid_value: str | None) -> LocalRecord:
        return LocalRecord.resolve(service, pid_value, with_drafts=False)

    assert resolve(None).state is LocalState.ABSENT
    assert resolve("unknown-pid").state is LocalState.ABSENT

    pid_value = service.create(
        system_identity, {"metadata": {"title": {"value": "Record 1"}}, "files": {"enabled": False}}
    )["id"]
    local = resolve(pid_value)
    assert local.state is LocalState.LIVE
    assert local.record["id"] == pid_value
    assert local.is_rdm is False

    service.delete(system_identity, pid_value)
    local = resolve(pid_value)
    assert local.state is LocalState.HARD_DELETED
    assert local.record is not None
    assert local.record.is_deleted


def test_resolve_local_rdm_record(app, db, search_clear, rdm_test_model, location, rdm_record_data):
    service = current_runtime.models["rdmtest"].service

    def resolve(pid_value: str | None) -> LocalRecord:
        return LocalRecord.resolve(service, pid_value, with_drafts=True)

    draft = service.create(system_identity, rdm_record_data)
    pid_value = draft["id"]
    local = resolve(pid_value)
    assert local.state is LocalState.DRAFT_ONLY
    assert local.draft is not None

    service.publish(system_identity, pid_value)
    local = resolve(pid_value)
    assert local.state is LocalState.LIVE
    assert local.record is not None
    assert local.is_rdm is True

    service.delete_record(system_identity, pid_value, {"note": "deleted locally"})
    local = resolve(pid_value)
    assert local.state is LocalState.TOMBSTONED
    assert local.record.deletion_status.is_deleted
