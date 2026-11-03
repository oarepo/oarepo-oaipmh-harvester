# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""A fallback harvester (`skip-if-owned`) and a repository harvester bringing the same pid."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from invenio_access.permissions import system_identity
from invenio_db import db
from invenio_vocabularies.datastreams.datastreams import StreamEntry

from oarepo_oaipmh_harvester.oai_record.models import OAIHarvestedRecord
from oarepo_oaipmh_harvester.proxies import current_oai_harvester_service
from oarepo_oaipmh_harvester.transformers import SkipIfOwnedTransformer
from oarepo_oaipmh_harvester.writers.oai_service import (
    LocalRecord,
    LocalState,
    OAIServiceWriter,
    Operation,
)

MODEL = "extpidtest"
PID = "doi-1"
REPO_OAI_ID = "oai:repo:1"
FALLBACK_OAI_ID = "oai:datacite:1"


@pytest.fixture
def fallback_harvester(app, db, harvester):
    current_oai_harvester_service.create(
        system_identity,
        {
            "id": "datacite",
            "name": "Fallback Harvester",
            "base_url": "https://oai.datacite.org/oai",
            "metadata_prefix": "oai_datacite",
            "setspec": "",
            "loader": "oai-pmh",
            "transformers": [f'oai-import{{"model":"{MODEL}"}}', f'skip-if-owned{{"model":"{MODEL}"}}'],
            "writers": [f'oai-service{{"model":"{MODEL}"}}'],
            "harvest_managers": [],
        },
    )
    db.session.commit()
    return "datacite"


class Harvest:
    """Write entries of the repository harvester (`test`) and the fallback harvester (`datacite`)."""

    def __init__(self, rdm_record_data: dict, fallback_harvester: str, repo_harvester: str):
        """Create the writers of both harvesters and the transformer of the fallback one."""
        self.rdm_record_data = rdm_record_data
        self.repo_writer = OAIServiceWriter(MODEL, harvester_id=repo_harvester)
        self.fallback_writer = OAIServiceWriter(MODEL, harvester_id=fallback_harvester)
        self.skip = SkipIfOwnedTransformer(MODEL, harvester_id=fallback_harvester)
        self.service = self.repo_writer.service

    def _entry(self, oai_identifier: str, day: int, title: str | None) -> StreamEntry:
        header = SimpleNamespace(
            identifier=oai_identifier, datestamp=dt.datetime(2025, 1, day, tzinfo=dt.UTC), deleted=title is None
        )
        record = (
            None
            if title is None
            else {**self.rdm_record_data, "id": PID, "metadata": {**self.rdm_record_data["metadata"], "title": title}}
        )
        return StreamEntry({"oai_record": SimpleNamespace(header=header, raw="<record/>"), "record": record})

    def repo(self, day: int, title: str | None) -> StreamEntry:
        """Harvest the repository record; `title=None` - deleted at the source."""
        entry = self.repo_writer.write(self._entry(REPO_OAI_ID, day, title))
        assert not entry.errors
        assert entry.exc is None
        return entry

    def fallback(self, day: int, title: str | None) -> StreamEntry:
        """Harvest the fallback record (transformer + writer); `title=None` - deleted at the source."""
        entry = self.fallback_writer.write(self.skip.apply(self._entry(FALLBACK_OAI_ID, day, title)))
        assert not entry.errors
        assert entry.exc is None
        return entry

    def title(self) -> str:
        """Title of the local record."""
        return self.service.read(system_identity, PID)["metadata"]["title"]

    def state(self) -> LocalState:
        """State of the local record."""
        return LocalRecord.resolve(self.service, PID, with_drafts=True).state


def _harvest_record(oai_identifier: str) -> OAIHarvestedRecord:
    return db.session.query(OAIHarvestedRecord).filter_by(oai_identifier=oai_identifier).one()


@pytest.fixture
def harvest(app, db, search_clear, external_pid_test_model, location, harvester, fallback_harvester, rdm_record_data):
    return Harvest(rdm_record_data, fallback_harvester, harvester)


def test_fallback_skipped_when_repository_came_first(harvest):
    assert harvest.repo(1, "Repo").op_type == Operation.CREATE

    entry = harvest.fallback(1, "Fallback")
    assert entry.filtered
    assert entry.op_type is None
    assert entry.entry["record"] is None
    assert harvest.title() == "Repo"

    stored = _harvest_record(FALLBACK_OAI_ID)
    assert stored.has_errors is False
    assert stored.has_warnings is True
    assert stored.errors == [
        {"type": "skipped", "location": "", "message": f"Record {PID} is harvested by harvester test ({REPO_OAI_ID})"}
    ]

    # deleted at the fallback source - never written by it, so nothing to delete
    assert harvest.fallback(2, None).op_type == Operation.NOOP
    assert harvest.state() is LocalState.LIVE
    assert harvest.title() == "Repo"


def test_repository_overrides_fallback(harvest):
    assert not harvest.fallback(1, "Fallback").filtered
    assert harvest.title() == "Fallback"

    assert harvest.repo(1, "Repo").op_type == Operation.UPDATE
    assert harvest.title() == "Repo"

    # changed at the fallback source - still skipped
    assert harvest.fallback(2, "Fallback v2").filtered
    assert harvest.title() == "Repo"
    # deleted at the fallback source - the repository record stays
    assert harvest.fallback(3, None).filtered
    assert harvest.state() is LocalState.LIVE


def test_fallback_takes_over_after_repository_deletion(harvest):
    harvest.repo(1, "Repo")
    assert harvest.fallback(1, "Fallback").filtered

    assert harvest.repo(2, None).op_type == Operation.DELETE_RECORD
    assert harvest.state() is LocalState.TOMBSTONED

    # same datestamp as before - a skipped harvest record is never up to date
    entry = harvest.fallback(1, "Fallback")
    assert not entry.filtered
    assert entry.op_type == Operation.RESTORE
    assert harvest.title() == "Fallback"
    stored = _harvest_record(FALLBACK_OAI_ID)
    assert stored.has_warnings is False
    assert stored.errors == []


def test_deleted_fallback_record_never_written_is_noop(harvest):
    entry = harvest.fallback(1, None)
    assert not entry.filtered
    assert entry.op_type == Operation.NOOP
    assert harvest.state() is LocalState.ABSENT


def test_skipped_records_do_not_own_the_pid(harvest):
    """Two fallback harvesters must not skip each other forever."""
    harvest.repo(1, "Repo")
    assert harvest.fallback(1, "Fallback").filtered
    harvest.repo(2, None)

    # the repository harvester, seen as another fallback, is not blocked by the skipped record
    other = SkipIfOwnedTransformer(MODEL, harvester_id="test")
    assert not other.apply(harvest._entry(REPO_OAI_ID, 3, "Repo v2")).filtered
