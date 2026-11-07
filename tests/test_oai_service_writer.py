# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""The `oai-service` writer - harvested versions of one record against the local record they make."""

from __future__ import annotations

import datetime as dt
from unittest.mock import ANY

import marshmallow as ma
import pytest
from invenio_access.permissions import system_identity
from invenio_db import db
from invenio_pidstore.models import PersistentIdentifier, PIDStatus
from invenio_rdm_records.proxies import current_rdm_records
from invenio_rdm_records.services.errors import ValidationErrorWithMessageAsList
from oarepo_runtime import current_runtime

from oarepo_oaipmh_harvester.oai_record.dumpers import MAX_KEYWORD_LENGTH, ErrorsFacetDumperExt
from oarepo_oaipmh_harvester.proxies import current_oai_record_service
from oarepo_oaipmh_harvester.writers.oai_service import (
    LocalRecord,
    LocalState,
    OAIServiceWriter,
    Operation,
    _utc_datestamp,
)

OAI_ID = "oai:test:1"
PID = "ext-1"


class Harvests:
    """Harvested versions of one OAI record written by a writer, and the local record they make."""

    def __init__(self, writer: OAIServiceWriter, make_record, oai_entry, harvest_record, *, drafts: bool):
        """Remember the writer and how to build the record data of a version."""
        self.writer = writer
        self.service = writer.service
        self.make_record = make_record
        self._oai_entry = oai_entry
        self._harvest_record = harvest_record
        self._drafts = drafts

    def write(self, day: int, title: str | None = None, *, record: dict | None = None, **extra):
        """Write the version of `day`; without a title it is deleted at the source. Return the entry."""
        if record is None and title is not None:
            record = self.make_record(title, **extra)
        return self.writer.write(self._oai_entry(OAI_ID, day, record))

    def __call__(self, day: int, title: str | None = None, **kwargs) -> Operation | None:
        """Write the version of `day`, assert it succeeded and return the operation (`None` - up to date)."""
        entry = self.write(day, title, **kwargs)
        assert not entry.errors, entry.errors
        assert entry.exc is None, entry.exc
        assert not self.harvest_record.has_errors, self.harvest_record.errors
        return entry.op_type

    @property
    def harvest_record(self):
        """The stored harvest record of the OAI record."""
        return self._harvest_record(OAI_ID)

    @property
    def pid(self) -> str:
        """Pid of the local record."""
        return self.harvest_record.record_pid

    def title(self):
        """Title of the local record."""
        return self.service.read(system_identity, self.pid)["metadata"]["title"]

    def local(self) -> LocalRecord:
        """State of the local record."""
        return LocalRecord.resolve(self.service, self.pid, with_drafts=self._drafts)

    def edit_locally(self) -> None:
        """Create a local edit draft of the published record (not published)."""
        self.service.edit(system_identity, self.pid)
        self.service.update_draft(system_identity, self.pid, self.make_record("Local edit"))
        db.session.commit()


@pytest.fixture
def harvests(app, db, search_clear, location, harvester, rdm_record_data, oai_entry, harvest_record):
    """Return `Harvests` of a model - `test` (plain records) or an rdm one - with writer options."""

    def _harvests(model: str = "rdmtest", **writer_options) -> Harvests:
        plain = model == "test"

        def make_record(title: str, **extra) -> dict:
            if plain:
                return {"metadata": {"title": {"value": title}}, "files": {"enabled": False}, **extra}
            return {**rdm_record_data, "metadata": {**rdm_record_data["metadata"], "title": title}, **extra}

        writer = OAIServiceWriter(model, publish=not plain, harvester_id=harvester, **writer_options)
        return Harvests(writer, make_record, oai_entry, harvest_record, drafts=not plain)

    return _harvests


@pytest.fixture
def rdm(harvests) -> Harvests:
    """`Harvests` of the rdm test model."""
    return harvests()


def test_harvest_wins_plain_model(harvests):
    plain = harvests("test")

    assert plain(1, "Record 1") == Operation.CREATE
    pid = plain.pid

    assert plain(2) == Operation.DELETE
    assert (plain.harvest_record.datestamp, plain.harvest_record.deleted) == (
        dt.datetime(2025, 1, 2, tzinfo=dt.UTC),
        True,
    )
    assert plain.local().state is LocalState.HARD_DELETED
    assert plain(3) == Operation.NOOP

    # a hard deleted record is revived with its original pid
    assert plain(4, "Record 2") == Operation.REVIVE
    assert plain.pid == pid
    assert plain.title() == {"value": "Record 2"}


def test_harvest_wins_rdm_model(rdm):
    assert rdm(1, "Title v1") == Operation.CREATE
    pid = rdm.pid
    assert rdm(2, "Title v2") == Operation.UPDATE
    assert rdm.title() == "Title v2"

    assert rdm(3) == Operation.DELETE_RECORD
    assert rdm.local().state is LocalState.TOMBSTONED
    assert rdm.local().record.tombstone.note == f"Deleted at the OAI-PMH source ({OAI_ID})"
    assert rdm(4) == Operation.NOOP

    assert rdm(5, "Title v3") == Operation.RESTORE
    assert (rdm.pid, rdm.title()) == (pid, "Title v3")


def test_sync_index_false_queues_the_harvest_record(harvests, mocker):
    """`sync_index:false` (the window tasks of a parallel harvest) queues instead of indexing."""
    bulk_index = mocker.patch.object(type(current_oai_record_service.indexer), "bulk_index")

    harvests("test", sync_index=False)(1, "Record 1")

    bulk_index.assert_called_once_with([OAI_ID])


def test_resolve_local_record(app, db, search_clear, location):
    service = current_runtime.models["test"].service

    def resolve(pid_value: str | None) -> LocalRecord:
        return LocalRecord.resolve(service, pid_value, with_drafts=False)

    assert resolve(None).state is LocalState.ABSENT
    assert resolve("unknown-pid").state is LocalState.ABSENT

    pid_value = service.create(
        system_identity, {"metadata": {"title": {"value": "Record 1"}}, "files": {"enabled": False}}
    )["id"]
    local = resolve(pid_value)
    assert (local.state, local.record["id"], local.is_rdm) == (LocalState.LIVE, pid_value, False)

    service.delete(system_identity, pid_value)
    local = resolve(pid_value)
    assert local.state is LocalState.HARD_DELETED
    assert local.record.is_deleted


def test_resolve_local_rdm_record(app, db, search_clear, location, rdm_record_data):
    service = current_runtime.models["rdmtest"].service

    def resolve(pid_value: str | None) -> LocalRecord:
        return LocalRecord.resolve(service, pid_value, with_drafts=True)

    pid_value = service.create(system_identity, rdm_record_data)["id"]
    local = resolve(pid_value)
    assert local.state is LocalState.DRAFT_ONLY
    assert local.draft is not None

    service.publish(system_identity, pid_value)
    local = resolve(pid_value)
    assert (local.state, local.is_rdm) == (LocalState.LIVE, True)

    service.delete_record(system_identity, pid_value, {"note": "deleted locally"})
    local = resolve(pid_value)
    assert local.state is LocalState.TOMBSTONED
    assert local.record.deletion_status.is_deleted


def test_harvest_restores_record_marked_for_purge(rdm):
    rdm(1, "Title v1")
    # deleted and marked for purge locally, not at the source
    rdm.service.delete_record(system_identity, rdm.pid, {"note": "local delete"})
    rdm.service.mark_record_for_purge(system_identity, rdm.pid)

    assert rdm(2, "Title v2") == Operation.RESTORE
    assert rdm.title() == "Title v2"


def test_failed_update_rolls_back_restore(rdm):
    rdm(1, "Title v1")
    rdm(2)

    # title too short - validation error during the update following the restore
    assert rdm.write(3, "v2").errors
    assert rdm.harvest_record.has_errors is True
    assert rdm.local().state is LocalState.TOMBSTONED


def test_harvest_revives_hard_deleted_rdm_record(rdm):
    rdm(1, "Title v1")
    pid = rdm.pid
    parent_id = rdm.service.read(system_identity, pid)["parent"]["id"]
    # hard delete, as done by previous versions of the writer
    rdm.service.delete(system_identity, pid)
    db.session.commit()
    # cleanup_drafts celery beat task (hourly) hard deletes the soft-deleted draft row
    rdm.service.cleanup_drafts(dt.timedelta(0), search_gc_deletes=0)
    db.session.commit()
    assert rdm.service.draft_cls.model_cls.query.filter_by(id=rdm.local().record.id).count() == 0

    assert rdm(2, "Title v2") == Operation.REVIVE
    # model pid and oarepo-rdm global "recid" pid are both registered again
    assert all(p.status == PIDStatus.REGISTERED for p in PersistentIdentifier.query.filter_by(pid_value=pid))
    read = rdm.service.read(system_identity, pid)
    assert (read["metadata"]["title"], read["parent"]["id"]) == ("Title v2", parent_id)


def test_unchanged_harvest_still_wins_over_local_changes(rdm):
    # live at the source, deleted locally - same datestamp is re-harvested, record restored
    rdm(1, "Title v1")
    assert rdm(1, "Title v1") is None  # up to date, skipped
    rdm.service.delete_record(system_identity, rdm.pid, {"note": "local delete"})
    assert rdm(1, "Title v1") == Operation.RESTORE
    assert rdm.local().state is LocalState.LIVE

    # deleted at the source, restored locally (e.g. user moderation restore) - deleted again
    rdm(2)
    assert rdm(2) is None  # up to date, skipped
    rdm.service.restore_record(system_identity, rdm.pid)
    assert rdm(2) == Operation.DELETE_RECORD
    assert rdm.local().state is LocalState.TOMBSTONED


@pytest.mark.parametrize(
    ("deleted_locally", "operation"),
    [(False, Operation.DELETE_RECORD), (True, Operation.DELETE_DRAFT)],
    ids=["live", "deleted-locally"],
)
def test_source_deletion_removes_the_local_edit_draft(rdm, deleted_locally, operation):
    rdm(1, "Title v1")
    rdm.edit_locally()
    if deleted_locally:
        rdm.service.delete_record(system_identity, rdm.pid, {"note": "local delete"})
        db.session.commit()

    assert rdm(2) == operation
    assert (rdm.local().state, rdm.local().draft) == (LocalState.TOMBSTONED, None)
    assert rdm(2) is None  # up to date now


def test_unchanged_harvest_overwrites_local_edit_draft(rdm):
    rdm(1, "Title v1")
    rdm.edit_locally()

    assert rdm(1, "Title v1") == Operation.UPDATE
    assert (rdm.title(), rdm.local().draft) == ("Title v1", None)
    assert rdm(1, "Title v1") is None  # up to date now


@pytest.mark.parametrize("published", [False, True], ids=["user_draft", "user_published"])
def test_harvest_overwrites_user_record_with_same_external_pid(harvests, published):
    """User deposited a record with an external pid, the harvest brings the same pid later."""
    ext = harvests("extpidtest")
    ext.service.create(system_identity, ext.make_record("User title", id=PID))
    if published:
        ext.service.publish(system_identity, PID)
    db.session.commit()

    assert ext(1, "Harvested title", id=PID) == (Operation.UPDATE if published else Operation.UPDATE_DRAFT)

    # harvested data overwrote the user's record, no new record was created
    assert (ext.pid, ext.title()) == (PID, "Harvested title")
    # oarepo-rdm keeps a global "recid" pid next to the model pid - both must point to the same record
    assert len({p.object_uuid for p in PersistentIdentifier.query.filter_by(pid_value=PID)}) == 1
    assert ext.service.record_cls.model_cls.query.count() == 1
    assert ext.local().draft is None


def test_direct_update(harvests, mocker):
    """direct_update=True updates the published record via service.update, without a draft round trip."""
    ext = harvests("extpidtest", direct_update=True)
    # direct update (base records service) requires media_files - NMA transformers always send it
    version = {"id": PID, "media_files": {"enabled": False}}

    assert ext(1, "Title v1", **version) == Operation.CREATE
    revision_id = ext.service.read(system_identity, PID)["revision_id"]
    ext.edit_locally()
    edit = mocker.spy(ext.service, "edit")
    publish = mocker.spy(ext.service, "publish")

    assert ext(2, "Title v2", **version) == Operation.UPDATE
    edit.assert_not_called()
    publish.assert_not_called()
    assert ext.title() == "Title v2"
    assert ext.service.read(system_identity, PID)["revision_id"] > revision_id
    # the local edit draft does not survive the harvest
    assert ext.local().draft is None
    assert ext(2, "Title v2", **version) is None  # up to date


def test_harvest_adds_record_to_communities(harvests, communities, mocker):
    """Records go to the writer's community and to the ones listed in parent.communities.ids."""
    communities("writer-community", "listed-community")
    # the test model has its own parent table, invenio's bulk_add can not store the membership here
    bulk_add = mocker.patch.object(current_rdm_records.record_communities_service, "bulk_add", return_value=[])
    parent = {"communities": {"ids": ["listed-community", "writer-community"]}}
    rdm = harvests(community="writer-community")

    assert rdm(1, "Title v1", parent=parent) == Operation.CREATE
    # the writer's community first, duplicates removed
    assert [call.args for call in bulk_add.call_args_list] == [
        (system_identity, "writer-community", [rdm.pid]),
        (system_identity, "listed-community", [rdm.pid]),
    ]
    # transformed data is stored as produced by the transformer
    assert rdm.harvest_record.transformed_data["parent"] == parent


@pytest.mark.parametrize(
    ("community", "bulk_add_errors", "message"),
    [
        ("writer-community", [{"message": "Community already included."}], "Community already included."),
        ("unknown", None, "Community 'unknown' does not exist"),
    ],
    ids=["bulk-add-fails", "unknown-community"],
)
def test_community_failure_rolls_back_the_write(harvests, communities, mocker, community, bulk_add_errors, message):
    communities("writer-community")
    if bulk_add_errors is not None:
        mocker.patch.object(current_rdm_records.record_communities_service, "bulk_add", return_value=bulk_add_errors)
    rdm = harvests(community=community)

    entry = rdm.write(1, "Title v1")

    # reported to the datastream as well as stored on the harvest record
    assert message in str(entry.exc)
    assert message in rdm.harvest_record.errors[0]["message"]
    # the whole write was rolled back
    assert rdm.pid is None
    assert rdm.service.record_cls.model_cls.query.count() == 0


@pytest.mark.parametrize(
    ("model", "options", "match"),
    [("rdmtest", {"publish": False}, "publish=True"), ("test", {"publish": False, "community": "c"}, "communities")],
    ids=["rdm-model-needs-publish", "community-needs-rdm-model"],
)
def test_invalid_writer_options(app, model, options, match):
    with pytest.raises(ValueError, match=match):
        OAIServiceWriter(model, **options)


def test_files_disabled_when_not_in_record(rdm):
    """Harvested metadata without a files section are published as metadata-only records."""
    record = {key: value for key, value in rdm.make_record("Title v1").items() if key != "files"}

    assert rdm(1, record=record) == Operation.CREATE
    read = rdm.service.read(system_identity, rdm.pid).to_dict()
    assert read["files"]["enabled"] is False
    if current_runtime.models["rdmtest"].media_file_service is not None:
        assert read["media_files"]["enabled"] is False
    # stored as produced by the transformer
    assert "files" not in rdm.harvest_record.transformed_data


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


def test_errors_are_faceted_in_search_document():
    """Long messages and tracebacks would exceed the keyword `ignore_above` and not be indexed."""
    data = {
        "errors": [
            {
                "type": "IntegrityError",
                "message": "(psycopg2.errors.ForeignKeyViolation) insert or update\n violates " + "x" * 1000,
                "location": "write@a.py:1\n    self = <writer>\n_flush@b.py:2\n    x = 1",
            },
            {"type": "KeyError", "message": "", "location": "f@c.py:3"},
            {"type": "validation_error", "message": "Missing data", "location": "metadata.title"},
        ]
    }
    ErrorsFacetDumperExt().dump(None, data)
    long_error, empty_error, validation_error = data["errors"]
    assert len(long_error["message"]) == MAX_KEYWORD_LENGTH
    assert long_error["message"].startswith("(psycopg2.errors.ForeignKeyViolation) insert or update violates")
    assert long_error["message"].endswith("…")
    assert long_error["location"] == "_flush@b.py:2"  # innermost frame
    assert empty_error["message"] == "KeyError (no message)"
    assert validation_error == {"type": "validation_error", "message": "Missing data", "location": "metadata.title"}


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        # an empty message gets a placeholder; the location is the traceback
        (KeyError(), [(ANY, "KeyError (no message)")]),
        # str() of this one is "['Missing uploaded files...']"
        (
            ma.ValidationError(["Missing uploaded files."], field_name="files.enabled"),
            [("files.enabled", "Missing uploaded files.")],
        ),
        (
            ma.ValidationError({"metadata": {"terms_of_use": {"license": ["Missing iri"]}}}),
            [("metadata.terms_of_use.license", "Missing iri")],
        ),
        (ma.ValidationError("Plain message"), [("", "Plain message")]),
        (
            ValidationErrorWithMessageAsList([{"field": "metadata.title", "messages": ["Too short.", "Missing."]}]),
            [("metadata.title", "Too short."), ("metadata.title", "Missing.")],
        ),
    ],
)
def test_exception_gives_error_per_message(exception, expected):
    errors = OAIServiceWriter.__new__(OAIServiceWriter)._convert_exception_to_errors(exception)
    assert [(e["location"], e["message"]) for e in errors] == expected
    assert all(e["type"] == type(exception).__name__ for e in errors)


def test_service_validation_error_with_string_messages():
    writer = OAIServiceWriter.__new__(OAIServiceWriter)
    errors = list(writer._convert_to_oai_error({"field": "files", "messages": "Not a list"}))
    assert errors == [{"type": "validation_error", "location": "files", "message": "Not a list"}]
