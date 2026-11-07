# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Sequential harvest - `harvest_oaipmh_records` and the REST "Run" action against the fake source."""

from __future__ import annotations

import datetime as dt
from urllib.parse import urlparse

import pytest
from invenio_db import db
from invenio_vocabularies.datastreams.datastreams import StreamEntry
from invenio_vocabularies.datastreams.errors import TransformerError
from invenio_vocabularies.datastreams.transformers import BaseTransformer

from oarepo_oaipmh_harvester.datastream import CatchingTransformer
from oarepo_oaipmh_harvester.oai_record.models import OAIHarvestedRecord
from oarepo_oaipmh_harvester.tasks import harvest_oaipmh_records
from oarepo_oaipmh_harvester.writers.oai_service import OAIServiceWriter

pytestmark = pytest.mark.usefixtures("location", "test_model")


def test_harvest_follows_the_source(app, source, harvester, harvested, harvest_record):
    kept, deleted = source.extend(["2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"])
    harvest_oaipmh_records(harvester_id=harvester)
    assert harvested() == {kept, deleted}

    source.update(kept, "2025-02-01T00:00:00Z", title="updated")
    source.delete(deleted, "2025-02-01T00:00:00Z")
    harvest_oaipmh_records(harvester_id=harvester)

    assert harvested() == {"updated"}
    assert harvest_record(deleted).deleted is True


def test_a_failed_record_is_stored_and_reported(
    app, source, harvester, harvest_manager, harvested, outbox, caplog, harvest_record
):
    """A record that can not be imported fails alone: stored on its harvest record, logged, mailed."""
    ok = source.add("2025-01-01T00:00:00Z")
    # two titles - the oai_dc import of the test model rejects the record; the markup in the
    # identifier comes from the source and must be escaped in the html mail
    broken = source.add("2025-01-02T00:00:00Z", identifier="oai:test:<b>2</b>", title=["one", "two"])

    harvest_oaipmh_records(harvester_id=harvester)

    assert harvested() == {ok}
    failed = harvest_record(broken)
    assert (failed.has_errors, failed.record_pid, failed.errors[0]["type"]) == (True, None, "ValueError")
    assert "not repeatable" in failed.errors[0]["message"]
    assert f"Entry {broken}: failed: ValueError" in caplog.text

    (mail,) = outbox
    assert mail.recipients == [harvest_manager.email]
    assert mail.subject == "Harvest of Test Harvester finished with 1 failed and 1 ok record(s)"
    assert broken in mail.body
    assert "oai:test:&lt;b&gt;2&lt;/b&gt;" in mail.html
    assert "<b>2</b>" not in mail.html
    assert "/oarepo/harvest/records/" in mail.html


def test_errors_reported_by_a_transformer_fail_the_record(app):
    """A transformer may report errors instead of raising - they are turned into an exception."""

    class Reporting(BaseTransformer):
        def apply(self, stream_entry, *_args, **_kwargs):
            stream_entry.errors.append("bad license")
            return stream_entry

    entry = CatchingTransformer(Reporting()).apply(StreamEntry({"record": None}))

    assert isinstance(entry.exc, TransformerError)
    assert "bad license" in str(entry.exc)
    assert entry.errors == []


def test_writer_exception_does_not_stop_harvest(app, source, harvester, mocker, harvest_record):
    """An exception escaping the writer (here: storing the harvest record) affects only its record."""
    failing, other = source.extend(["2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z"])
    get_oai_record = OAIServiceWriter._get_oai_record

    def hiccup(self, oai_identifier):
        if oai_identifier == failing:
            raise RuntimeError("database hiccup")
        return get_oai_record(self, oai_identifier)

    mocker.patch.object(OAIServiceWriter, "_get_oai_record", hiccup)

    harvest_oaipmh_records(harvester_id=harvester)

    assert db.session.query(OAIHarvestedRecord).filter_by(oai_identifier=failing).count() == 0
    assert harvest_record(other).has_errors is False


def test_no_report_without_managers(app, source, harvester, outbox):
    source.add("2025-01-01T00:00:00Z")

    harvest_oaipmh_records(harvester_id=harvester)

    assert outbox == []


def test_empty_incremental_harvest_succeeds(app, source, harvester, harvest_manager, harvested, outbox):
    """Nothing new since the last run (a quiet scheduled harvest) is neither an error nor a mail."""
    source.add("2025-01-01T00:00:00Z")

    harvest_oaipmh_records(harvester_id=harvester, since=dt.datetime.now(dt.UTC))

    assert harvested() == set()
    assert outbox == []


def test_run_action(app, source, harvester, harvested, user_with_administration_rights, client):
    """The administration "Run" action harvests everything, or only what changed since the last harvest."""
    source.extend(["2025-01-01T00:00:00Z", "2025-01-05T00:00:00Z"])
    user_with_administration_rights.api_login(client)
    links = client.get(f"/api/oai/harvest/harvesters/{harvester}").get_json()["links"]
    assert links["self"].endswith(f"/api/oai/harvest/harvesters/{harvester}")
    # the session cookie belongs to the test client's host - post to the path of the link
    run = urlparse(links["actions"]["harvest"]).path
    assert run == f"/api/oai/harvest/harvesters/{harvester}/start"

    # celery is eager in the tests - the harvest runs within the request
    assert client.post(run, json={"all_records": True}).status_code == 200
    assert harvested() == source.identifiers

    new = source.add("2025-02-01T00:00:00Z")
    assert client.post(run, json={"all_records": False}).status_code == 200
    # modified records only: from the newest datestamp harvested before
    list_records = [request for request in source.requests if request["verb"] == "ListRecords"]
    assert list_records[-1]["from"] == "2025-01-05T00:00:00Z"
    assert new in harvested()
