# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from invenio_access.permissions import system_identity
from invenio_indexer.tasks import process_bulk_queue
from oarepo_runtime import current_runtime

from oarepo_oaipmh_harvester.proxies import (
    current_oai_record_service,
)
from oarepo_oaipmh_harvester.tasks import harvest_oaipmh_records


class OAIPMHResponses:
    """Mock OAI-PMH responses from files."""

    def __init__(self, base_path: Path):
        """Initialize the mock OAI-PMH responses from files."""
        self.base_path = base_path
        self.responses: dict[str, list[bytes]] = {}
        for f in sorted(base_path.iterdir()):
            if f.is_file() and f.suffix == ".xml":
                parts = f.stem.split("_")
                verb = parts[0]
                if verb not in self.responses:
                    self.responses[verb] = []
                self.responses[verb].append(f.read_bytes())

    def __call__(self, params):
        """Mock the OAI-PMH responses based on the verb."""
        verb = params["verb"]
        if verb not in self.responses or not self.responses[verb]:
            raise ValueError(f"No more responses for verb {params}")
        return Mock(status_code=200, content=self.responses[verb].pop(0))


@pytest.fixture
def test_service(app, test_model):
    return current_runtime.models["test"].service


def test_harvest_task(app, db, search_clear, test_model, test_service, location, harvester, mocker):
    mocker.patch(
        "oaipmh_scythe.client.Scythe._request",
        side_effect=OAIPMHResponses(Path(__file__).parent / "oai_responses"),
    )

    harvest_oaipmh_records(harvester_id=harvester, since=None, batch_size=1)
    process_bulk_queue(indexer_name=test_service.config.service_id)
    process_bulk_queue(indexer_name="oai-harvest-record")
    test_service.indexer.refresh()
    results = test_service.search(system_identity).to_dict()
    assert results["hits"]["total"] == 1
    assert results["hits"]["hits"][0]["metadata"]["title"] == {"value": "Record 1 updated"}

    current_oai_record_service.indexer.refresh()
    current_oai_record_service.search(system_identity).to_dict()
    oai_results = current_oai_record_service.search(system_identity).to_dict()
    assert oai_results["hits"]["total"] == 2


def test_start_harvest_via_service(app, db, search_clear, harvester, mocker):
    from oarepo_oaipmh_harvester.proxies import current_oai_harvester_service

    delay = mocker.patch("oarepo_oaipmh_harvester.tasks.harvest_oaipmh_records.delay")
    current_oai_harvester_service.harvest(system_identity, harvester)
    # the task takes keyword arguments only
    delay.assert_called_once_with(harvester_id=harvester)


def test_harvest_continues_after_record_failure(
    app, db, search_clear, test_model, test_service, location, harvester, mocker, caplog
):
    """An exception transforming one record is stored on its harvest record, the harvest goes on."""
    import marshmallow as ma
    from invenio_db import db as _db

    from oarepo_oaipmh_harvester.oai_record.models import OAIHarvestedRecord
    from oarepo_oaipmh_harvester.transformers.oai_import import OAIImportTransformer

    mocker.patch(
        "oaipmh_scythe.client.Scythe._request",
        side_effect=OAIPMHResponses(Path(__file__).parent / "oai_responses"),
    )
    original_apply = OAIImportTransformer.apply

    def failing_apply(self, stream_entry, *args, **kwargs):
        if stream_entry.entry["record"].header.identifier == "oai:zenodo.org:1":
            raise ma.ValidationError({"metadata": {"license": ["Missing vocabulary iri"]}})
        return original_apply(self, stream_entry, *args, **kwargs)

    mocker.patch.object(OAIImportTransformer, "apply", failing_apply)

    harvest_oaipmh_records(harvester_id=harvester, since=None, batch_size=1)

    failed = _db.session.query(OAIHarvestedRecord).filter_by(oai_identifier="oai:zenodo.org:1").one()
    assert failed.has_errors is True
    assert failed.record_pid is None
    assert failed.errors[0]["type"] == "ValidationError"
    assert "Missing vocabulary iri" in failed.errors[0]["message"]

    # the other record was harvested (created, then deleted at the source)
    other = _db.session.query(OAIHarvestedRecord).filter_by(oai_identifier="oai:zenodo.org:2").one()
    assert other.has_errors is False
    assert other.deleted is True
    assert other.record_pid is not None

    # the failure is logged as such, with a short notice of the stored errors
    assert "Entry oai:zenodo.org:1: failed: ValidationError" in caplog.text
    assert "Entry oai:zenodo.org:1: processed successfully" not in caplog.text
    assert "OAI identifier oai:zenodo.org:1: 1 error(s) stored on the harvest record: ValidationError" in caplog.text


def test_transformer_errors_without_exception_are_stored(
    app, db, search_clear, test_model, test_service, location, harvester, mocker
):
    """Errors reported by a transformer in `errors` (not raised) end up on the harvest record too."""
    from invenio_db import db as _db

    from oarepo_oaipmh_harvester.oai_record.models import OAIHarvestedRecord
    from oarepo_oaipmh_harvester.transformers.oai_import import OAIImportTransformer

    mocker.patch(
        "oaipmh_scythe.client.Scythe._request",
        side_effect=OAIPMHResponses(Path(__file__).parent / "oai_responses"),
    )
    original_apply = OAIImportTransformer.apply

    def apply_with_errors(self, stream_entry, *args, **kwargs):
        result = original_apply(self, stream_entry, *args, **kwargs)
        if result.entry["oai_record"].header.identifier == "oai:zenodo.org:1":
            result.errors.append("bad license")
        return result

    mocker.patch.object(OAIImportTransformer, "apply", apply_with_errors)

    harvest_oaipmh_records(harvester_id=harvester, since=None, batch_size=1)

    failed = _db.session.query(OAIHarvestedRecord).filter_by(oai_identifier="oai:zenodo.org:1").one()
    assert failed.has_errors is True
    assert failed.record_pid is None
    assert failed.errors[0]["type"] == "TransformerError"
    assert "bad license" in failed.errors[0]["message"]


def test_writer_exception_does_not_stop_harvest(
    app, db, search_clear, test_model, test_service, location, harvester, mocker
):
    """An exception escaping the writer (here: storing the harvest record) affects only its record."""
    from invenio_db import db as _db

    from oarepo_oaipmh_harvester.oai_record.models import OAIHarvestedRecord
    from oarepo_oaipmh_harvester.writers.oai_service import OAIServiceWriter

    mocker.patch(
        "oaipmh_scythe.client.Scythe._request",
        side_effect=OAIPMHResponses(Path(__file__).parent / "oai_responses"),
    )
    original_get = OAIServiceWriter._get_oai_record

    def failing_get(self, oai_identifier):
        if oai_identifier == "oai:zenodo.org:1":
            raise RuntimeError("database hiccup")
        return original_get(self, oai_identifier)

    mocker.patch.object(OAIServiceWriter, "_get_oai_record", failing_get)

    harvest_oaipmh_records(harvester_id=harvester, since=None, batch_size=1)

    assert _db.session.query(OAIHarvestedRecord).filter_by(oai_identifier="oai:zenodo.org:1").count() == 0
    other = _db.session.query(OAIHarvestedRecord).filter_by(oai_identifier="oai:zenodo.org:2").one()
    assert other.has_errors is False
    assert other.deleted is True


def test_harvest_report_is_mailed_to_managers(
    app, db, search_clear, test_model, test_service, location, harvester, users, mocker
):
    """The harvest managers get a mail with the counts and links to the failed records."""
    from invenio_access.permissions import system_identity as _system_identity

    from oarepo_oaipmh_harvester.proxies import current_oai_harvester_service
    from oarepo_oaipmh_harvester.transformers.oai_import import OAIImportTransformer

    current_oai_harvester_service.update(
        _system_identity,
        harvester,
        {
            **current_oai_harvester_service.read(_system_identity, harvester).to_dict(),
            "harvest_managers": [{"user": str(users[0].id)}],
        },
    )
    mocker.patch(
        "oaipmh_scythe.client.Scythe._request",
        side_effect=OAIPMHResponses(Path(__file__).parent / "oai_responses"),
    )
    original_apply = OAIImportTransformer.apply

    def failing_apply(self, stream_entry, *args, **kwargs):
        if stream_entry.entry["record"].header.identifier == "oai:zenodo.org:1":
            raise ValueError("broken <b>metadata</b>")
        return original_apply(self, stream_entry, *args, **kwargs)

    mocker.patch.object(OAIImportTransformer, "apply", failing_apply)

    with app.extensions["mail"].record_messages() as outbox:
        harvest_oaipmh_records(harvester_id=harvester, since=None, batch_size=1)

    assert len(outbox) == 1
    mail = outbox[0]
    assert mail.recipients == [users[0].email]
    assert mail.subject == "Harvest of Test Harvester finished with 2 failed and 2 ok record(s)"
    assert "oai:zenodo.org:1: ValueError: broken <b>metadata</b>" in mail.body
    # values come from harvested data - escaped in the html part
    assert "broken &lt;b&gt;metadata&lt;/b&gt;" in mail.html
    assert "<b>metadata</b>" not in mail.html
    assert "/oarepo/harvest/records/oai:zenodo.org:1" in mail.html
    assert "Records processed successfully: 2" in mail.body


def test_no_report_without_managers(app, db, search_clear, test_model, location, harvester, mocker):
    mocker.patch(
        "oaipmh_scythe.client.Scythe._request",
        side_effect=OAIPMHResponses(Path(__file__).parent / "oai_responses"),
    )
    with app.extensions["mail"].record_messages() as outbox:
        harvest_oaipmh_records(harvester_id=harvester, since=None, batch_size=1)
    assert outbox == []


def test_harvest_modified_records_only(app, db, search_clear, harvester, mocker):
    """Harvesting modified records only starts from the newest datestamp already harvested."""
    from datetime import UTC, datetime

    from oarepo_oaipmh_harvester.oai_record.models import OAIHarvestedRecord
    from oarepo_oaipmh_harvester.proxies import current_oai_harvester_service

    delay = mocker.patch("oarepo_oaipmh_harvester.tasks.harvest_oaipmh_records.delay")

    # nothing harvested yet - everything
    current_oai_harvester_service.harvest(system_identity, harvester, all_records=False)
    delay.assert_called_once_with(harvester_id=harvester)

    for day in (1, 5):
        db.session.add(
            OAIHarvestedRecord(
                oai_identifier=f"oai:test:{day}",
                harvester_id=harvester,
                datestamp=datetime(2025, 1, day, tzinfo=UTC),
                harvested_at=datetime(2025, 2, 1, tzinfo=UTC),
                errors=[],
                original_data={},
                transformed_data={},
            )
        )
    db.session.commit()
    delay.reset_mock()
    current_oai_harvester_service.harvest(system_identity, harvester, all_records=False)
    delay.assert_called_once_with(harvester_id=harvester, since="2025-01-05T00:00:00+00:00")


def test_harvest_action_payload(app, db, search_clear, harvester, user_with_administration_rights, client, mocker):
    """The administration "Run" action posts `all_records`; without a payload everything is harvested."""
    delay = mocker.patch("oarepo_oaipmh_harvester.tasks.harvest_oaipmh_records.delay")
    user_with_administration_rights.api_login(client)

    # the administration posts to the action link of the harvester
    links = client.get(f"/api/oai/harvest/harvesters/{harvester}").get_json()["links"]
    assert links["self"].endswith(f"/api/oai/harvest/harvesters/{harvester}")
    assert links["actions"]["harvest"].endswith(f"/api/oai/harvest/harvesters/{harvester}/start")

    assert client.post(f"/api/oai/harvest/harvesters/{harvester}/start", json={"all_records": True}).status_code == 200
    delay.assert_called_once_with(harvester_id=harvester)
    delay.reset_mock()
    # nothing harvested yet, so modified-only harvests everything as well
    assert client.post(f"/api/oai/harvest/harvesters/{harvester}/start", json={"all_records": False}).status_code == 200
    delay.assert_called_once_with(harvester_id=harvester)
