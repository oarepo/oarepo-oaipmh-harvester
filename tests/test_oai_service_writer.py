# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from invenio_access.permissions import system_identity
from invenio_db import db
from invenio_pidstore.models import PersistentIdentifier, PIDStatus
from invenio_rdm_records.proxies import current_rdm_records
from invenio_vocabularies.datastreams.datastreams import StreamEntry
from oarepo_runtime import current_runtime

from oarepo_oaipmh_harvester.oai_record.models import OAIHarvestedRecord
from oarepo_oaipmh_harvester.writers.oai_service import (
    LocalRecord,
    LocalState,
    OAIServiceWriter,
    Operation,
    _utc_datestamp,
)


def _entry(datestamp: dt.datetime, *, deleted: bool, record: dict | None = None) -> StreamEntry:
    header = SimpleNamespace(identifier="oai:test:1", datestamp=datestamp, deleted=deleted)
    return StreamEntry(
        {
            "oai_record": SimpleNamespace(header=header, raw="<record/>"),
            "record": record or {"metadata": {"title": {"value": "Record 1"}}, "files": {"enabled": False}},
        }
    )


def _harvest(writer: OAIServiceWriter, day: int, *, deleted: bool = False, record: dict | None = None) -> str:
    """Write a harvested entry with a datestamp of the given day, return the operation performed."""
    datestamp = dt.datetime(2025, 1, day, tzinfo=dt.UTC)
    entry = writer.write(_entry(datestamp, deleted=deleted, record=record))
    assert not entry.errors, entry.errors
    # exceptions raised by the service are stored on the oai record only
    oai_record = db.session.query(OAIHarvestedRecord).filter_by(oai_identifier="oai:test:1").one()
    assert not oai_record.has_errors, oai_record.errors
    return entry.op_type


def _oai_record(db) -> OAIHarvestedRecord:
    return db.session.query(OAIHarvestedRecord).filter_by(oai_identifier="oai:test:1").one()


def test_existing_oai_record_gets_new_datestamp_and_deleted(app, db, search_clear, test_model, location, harvester):
    writer = OAIServiceWriter("test", publish=False, harvester_id=harvester)
    first = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    second = dt.datetime(2025, 2, 1, tzinfo=dt.UTC)

    writer.write(_entry(first, deleted=False))
    writer.write(_entry(second, deleted=True))

    oai_record = db.session.query(OAIHarvestedRecord).filter_by(oai_identifier="oai:test:1").one()
    assert oai_record.datestamp == second
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


def test_harvest_wins_plain_model(app, db, search_clear, test_model, location, harvester):
    writer = OAIServiceWriter("test", publish=False, harvester_id=harvester)
    service = writer.service

    assert _harvest(writer, 1) == Operation.CREATE
    pid_value = _oai_record(db).record_pid

    assert _harvest(writer, 2, deleted=True) == Operation.DELETE
    assert LocalRecord.resolve(service, pid_value, with_drafts=False).state is LocalState.HARD_DELETED
    assert _harvest(writer, 3, deleted=True) == Operation.NOOP

    # hard deleted record is revived with its original pid
    record = {"metadata": {"title": {"value": "Record 2"}}, "files": {"enabled": False}}
    assert _harvest(writer, 4, record=record) == Operation.REVIVE
    assert _oai_record(db).record_pid == pid_value
    assert service.read(system_identity, pid_value)["metadata"]["title"] == {"value": "Record 2"}


def _rdm_data(rdm_record_data: dict, title: str) -> dict:
    return {**rdm_record_data, "metadata": {**rdm_record_data["metadata"], "title": title}}


def test_harvest_wins_rdm_model(app, db, search_clear, rdm_test_model, location, harvester, rdm_record_data):
    writer = OAIServiceWriter("rdmtest", publish=True, harvester_id=harvester)
    service = writer.service

    assert _harvest(writer, 1, record=_rdm_data(rdm_record_data, "Title v1")) == Operation.CREATE
    pid_value = _oai_record(db).record_pid
    assert service.read(system_identity, pid_value)["metadata"]["title"] == "Title v1"

    assert _harvest(writer, 2, record=_rdm_data(rdm_record_data, "Title v2")) == Operation.UPDATE
    assert service.read(system_identity, pid_value)["metadata"]["title"] == "Title v2"

    assert _harvest(writer, 3, deleted=True) == Operation.DELETE_RECORD
    local = LocalRecord.resolve(service, pid_value, with_drafts=True)
    assert local.state is LocalState.TOMBSTONED
    assert local.record.tombstone.note == "Deleted at the OAI-PMH source (oai:test:1)"
    assert _harvest(writer, 4, deleted=True) == Operation.NOOP

    assert _harvest(writer, 5, record=_rdm_data(rdm_record_data, "Title v3")) == Operation.RESTORE
    assert _oai_record(db).record_pid == pid_value
    assert service.read(system_identity, pid_value)["metadata"]["title"] == "Title v3"


def test_harvest_restores_record_marked_for_purge(
    app, db, search_clear, rdm_test_model, location, harvester, rdm_record_data
):
    writer = OAIServiceWriter("rdmtest", publish=True, harvester_id=harvester)
    service = writer.service

    _harvest(writer, 1, record=_rdm_data(rdm_record_data, "Title v1"))
    pid_value = _oai_record(db).record_pid
    # deleted and marked for purge locally, not at the source
    service.delete_record(system_identity, pid_value, {"note": "local delete"})
    service.mark_record_for_purge(system_identity, pid_value)

    assert _harvest(writer, 2, record=_rdm_data(rdm_record_data, "Title v2")) == Operation.RESTORE
    assert service.read(system_identity, pid_value)["metadata"]["title"] == "Title v2"


def test_failed_update_rolls_back_restore(app, db, search_clear, rdm_test_model, location, harvester, rdm_record_data):
    writer = OAIServiceWriter("rdmtest", publish=True, harvester_id=harvester)
    service = writer.service

    _harvest(writer, 1, record=_rdm_data(rdm_record_data, "Title v1"))
    pid_value = _oai_record(db).record_pid
    _harvest(writer, 2, deleted=True)

    # title too short - validation error during the update following the restore
    entry = writer.write(
        _entry(dt.datetime(2025, 1, 3, tzinfo=dt.UTC), deleted=False, record=_rdm_data(rdm_record_data, "v2"))
    )
    assert entry.errors
    assert _oai_record(db).has_errors is True
    assert LocalRecord.resolve(service, pid_value, with_drafts=True).state is LocalState.TOMBSTONED


def test_harvest_revives_hard_deleted_rdm_record(
    app, db, search_clear, rdm_test_model, location, harvester, rdm_record_data
):
    writer = OAIServiceWriter("rdmtest", publish=True, harvester_id=harvester)
    service = writer.service

    _harvest(writer, 1, record=_rdm_data(rdm_record_data, "Title v1"))
    pid_value = _oai_record(db).record_pid
    parent_id = service.read(system_identity, pid_value)["parent"]["id"]
    # hard delete, as done by previous versions of the writer
    service.delete(system_identity, pid_value)
    db.session.commit()
    # cleanup_drafts celery beat task (hourly) hard deletes the soft-deleted draft row
    service.cleanup_drafts(dt.timedelta(0), search_gc_deletes=0)
    db.session.commit()
    record_id = LocalRecord.resolve(service, pid_value, with_drafts=True).record.id
    assert service.draft_cls.model_cls.query.filter_by(id=record_id).count() == 0

    assert _harvest(writer, 2, record=_rdm_data(rdm_record_data, "Title v2")) == Operation.REVIVE
    # model pid and oarepo-rdm global "recid" pid are both registered again
    assert all(p.status == PIDStatus.REGISTERED for p in PersistentIdentifier.query.filter_by(pid_value=pid_value))
    read = service.read(system_identity, pid_value)
    assert read["metadata"]["title"] == "Title v2"
    assert read["parent"]["id"] == parent_id


def test_rdm_model_requires_publish(app, rdm_test_model):
    with pytest.raises(ValueError, match="publish=True"):
        OAIServiceWriter("rdmtest", publish=False)


def test_unchanged_harvest_still_wins_over_local_changes(
    app, db, search_clear, rdm_test_model, location, harvester, rdm_record_data
):
    writer = OAIServiceWriter("rdmtest", publish=True, harvester_id=harvester)
    service = writer.service

    # live at the source, deleted locally - same datestamp is re-harvested, record restored
    _harvest(writer, 1, record=_rdm_data(rdm_record_data, "Title v1"))
    pid_value = _oai_record(db).record_pid
    assert _harvest(writer, 1, record=_rdm_data(rdm_record_data, "Title v1")) is None  # up to date, skipped
    service.delete_record(system_identity, pid_value, {"note": "local delete"})
    assert _harvest(writer, 1, record=_rdm_data(rdm_record_data, "Title v1")) == Operation.RESTORE
    assert LocalRecord.resolve(service, pid_value, with_drafts=True).state is LocalState.LIVE

    # deleted at the source, restored locally (e.g. user moderation restore) - deleted again
    _harvest(writer, 2, deleted=True)
    assert _harvest(writer, 2, deleted=True) is None  # up to date, skipped
    service.restore_record(system_identity, pid_value)
    assert _harvest(writer, 2, deleted=True) == Operation.DELETE_RECORD
    assert LocalRecord.resolve(service, pid_value, with_drafts=True).state is LocalState.TOMBSTONED


@pytest.mark.parametrize(
    ("datestamp", "expected"),
    [
        ("2025-01-02", dt.datetime(2025, 1, 2, tzinfo=dt.UTC)),
        ("2025-01-02T03:04:05Z", dt.datetime(2025, 1, 2, 3, 4, 5, tzinfo=dt.UTC)),
        ("2025-01-02T03:04:05+02:00", dt.datetime(2025, 1, 2, 1, 4, 5, tzinfo=dt.UTC)),
        (
            dt.datetime(2025, 1, 2, 3, 4, 5),  # noqa DTZ001 intended without the timezone
            dt.datetime(2025, 1, 2, 3, 4, 5, tzinfo=dt.UTC),
        ),
    ],
)
def test_utc_datestamp(datestamp, expected):
    parsed = _utc_datestamp(datestamp)
    assert parsed == expected
    assert parsed.tzinfo is dt.UTC


def _edit_locally(service, pid_value: str, rdm_record_data: dict) -> None:
    """Create a local edit draft of a published record (not published)."""
    service.edit(system_identity, pid_value)
    service.update_draft(system_identity, pid_value, _rdm_data(rdm_record_data, "Local edit"))
    db.session.commit()


def test_source_deletion_removes_local_edit_draft(
    app, db, search_clear, rdm_test_model, location, harvester, rdm_record_data
):
    writer = OAIServiceWriter("rdmtest", publish=True, harvester_id=harvester)
    service = writer.service

    _harvest(writer, 1, record=_rdm_data(rdm_record_data, "Title v1"))
    pid_value = _oai_record(db).record_pid
    _edit_locally(service, pid_value, rdm_record_data)
    assert LocalRecord.resolve(service, pid_value, with_drafts=True).draft is not None

    assert _harvest(writer, 2, deleted=True) == Operation.DELETE_RECORD
    local = LocalRecord.resolve(service, pid_value, with_drafts=True)
    assert local.state is LocalState.TOMBSTONED
    assert local.draft is None


def test_source_deletion_removes_draft_of_locally_tombstoned_record(
    app, db, search_clear, rdm_test_model, location, harvester, rdm_record_data
):
    writer = OAIServiceWriter("rdmtest", publish=True, harvester_id=harvester)
    service = writer.service

    _harvest(writer, 1, record=_rdm_data(rdm_record_data, "Title v1"))
    pid_value = _oai_record(db).record_pid
    _edit_locally(service, pid_value, rdm_record_data)
    service.delete_record(system_identity, pid_value, {"note": "local delete"})
    db.session.commit()

    assert _harvest(writer, 2, deleted=True) == Operation.DELETE_DRAFT
    local = LocalRecord.resolve(service, pid_value, with_drafts=True)
    assert local.state is LocalState.TOMBSTONED
    assert local.draft is None
    assert _harvest(writer, 2, deleted=True) is None  # up to date now


def test_unchanged_harvest_overwrites_local_edit_draft(
    app, db, search_clear, rdm_test_model, location, harvester, rdm_record_data
):
    writer = OAIServiceWriter("rdmtest", publish=True, harvester_id=harvester)
    service = writer.service

    _harvest(writer, 1, record=_rdm_data(rdm_record_data, "Title v1"))
    pid_value = _oai_record(db).record_pid
    _edit_locally(service, pid_value, rdm_record_data)

    assert _harvest(writer, 1, record=_rdm_data(rdm_record_data, "Title v1")) == Operation.UPDATE
    assert service.read(system_identity, pid_value)["metadata"]["title"] == "Title v1"
    assert LocalRecord.resolve(service, pid_value, with_drafts=True).draft is None
    assert _harvest(writer, 1, record=_rdm_data(rdm_record_data, "Title v1")) is None  # up to date now


@pytest.mark.parametrize("published", [False, True], ids=["user_draft", "user_published"])
def test_harvest_overwrites_user_record_with_same_external_pid(
    app, db, search_clear, external_pid_test_model, location, harvester, rdm_record_data, published
):
    """User deposited a record with an external pid, the harvest brings the same pid later."""
    writer = OAIServiceWriter("extpidtest", publish=True, harvester_id=harvester)
    service = writer.service
    pid_value = "ext-1"

    service.create(system_identity, {**_rdm_data(rdm_record_data, "User title"), "id": pid_value})
    if published:
        service.publish(system_identity, pid_value)
    db.session.commit()

    expected_operation = Operation.UPDATE if published else Operation.UPDATE_DRAFT
    assert _harvest(writer, 1, record={**_rdm_data(rdm_record_data, "Harvested title"), "id": pid_value}) == (
        expected_operation
    )

    # harvested data overwrote the user's record, no new record was created
    assert _oai_record(db).record_pid == pid_value
    assert service.read(system_identity, pid_value)["metadata"]["title"] == "Harvested title"
    # oarepo-rdm keeps a global "recid" pid next to the model pid - both must point to the same record
    assert len({p.object_uuid for p in PersistentIdentifier.query.filter_by(pid_value=pid_value)}) == 1
    assert service.record_cls.model_cls.query.count() == 1
    assert LocalRecord.resolve(service, pid_value, with_drafts=True).draft is None


def test_direct_update(app, db, search_clear, external_pid_test_model, location, harvester, rdm_record_data, mocker):
    """direct_update=True updates the published record via service.update, without a draft round trip."""
    writer = OAIServiceWriter("extpidtest", publish=True, direct_update=True, harvester_id=harvester)
    service = writer.service
    pid_value = "ext-1"

    def record(title: str) -> dict:
        # direct update (base records service) requires media_files - NMA transformers always send it
        return {**_rdm_data(rdm_record_data, title), "id": pid_value, "media_files": {"enabled": False}}

    assert _harvest(writer, 1, record=record("Title v1")) == Operation.CREATE
    revision_id = service.read(system_identity, pid_value)["revision_id"]

    _edit_locally(service, pid_value, rdm_record_data)
    assert writer.service is service  # spies below must see the writer's calls
    edit = mocker.spy(service, "edit")
    publish = mocker.spy(service, "publish")
    assert _harvest(writer, 2, record=record("Title v2")) == Operation.UPDATE
    edit.assert_not_called()
    publish.assert_not_called()

    read = service.read(system_identity, pid_value)
    assert read["metadata"]["title"] == "Title v2"
    assert read["revision_id"] > revision_id
    # the local edit draft does not survive the harvest
    assert LocalRecord.resolve(service, pid_value, with_drafts=True).draft is None
    assert _harvest(writer, 2, record=record("Title v2")) is None  # up to date


def test_harvest_adds_record_to_communities(
    app, db, search_clear, rdm_test_model, location, harvester, rdm_record_data, communities, mocker
):
    """Records go to the writer's community and to the ones listed in parent.communities.ids."""
    communities("writer-community", "listed-community")
    # the test model has its own parent table, invenio's bulk_add can not store the membership here
    bulk_add = mocker.patch.object(current_rdm_records.record_communities_service, "bulk_add", return_value=[])
    writer = OAIServiceWriter("rdmtest", publish=True, harvester_id=harvester, community="writer-community")
    parent = {"communities": {"ids": ["listed-community", "writer-community"]}}
    record = {**_rdm_data(rdm_record_data, "Title v1"), "parent": parent}

    assert _harvest(writer, 1, record=record) == Operation.CREATE
    pid_value = _oai_record(db).record_pid
    # writer's community first, duplicates removed
    assert [c.args[1:] for c in bulk_add.call_args_list] == [
        ("writer-community", [pid_value]),
        ("listed-community", [pid_value]),
    ]
    assert all(c.args[0] is system_identity and c.kwargs["uow"] is not None for c in bulk_add.call_args_list)
    # transformed data is stored as produced by the transformer
    assert _oai_record(db).transformed_data["parent"] == parent


def test_harvest_community_error_rolls_back(
    app, db, search_clear, rdm_test_model, location, harvester, rdm_record_data, communities, mocker
):
    communities("writer-community")
    mocker.patch.object(
        current_rdm_records.record_communities_service,
        "bulk_add",
        return_value=[{"message": "Community already included."}],
    )
    writer = OAIServiceWriter("rdmtest", publish=True, harvester_id=harvester, community="writer-community")
    writer.write(_entry(dt.datetime(2025, 1, 1, tzinfo=dt.UTC), deleted=False, record=rdm_record_data))
    oai_record = _oai_record(db)
    assert oai_record.has_errors is True
    assert "Community already included." in oai_record.errors[0]["message"]
    assert writer.service.record_cls.model_cls.query.count() == 0


def test_harvest_unknown_community_is_an_error(
    app, db, search_clear, rdm_test_model, location, harvester, rdm_record_data
):
    writer = OAIServiceWriter("rdmtest", publish=True, harvester_id=harvester, community="unknown")
    writer.write(_entry(dt.datetime(2025, 1, 1, tzinfo=dt.UTC), deleted=False, record=rdm_record_data))
    oai_record = _oai_record(db)
    assert oai_record.has_errors is True
    # the whole write was rolled back
    assert oai_record.record_pid is None
    assert writer.service.record_cls.model_cls.query.count() == 0


def test_community_requires_rdm_model(app, test_model):
    with pytest.raises(ValueError, match="communities"):
        OAIServiceWriter("test", publish=False, community="c")
