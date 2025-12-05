#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from invenio_access.permissions import system_identity
from invenio_indexer.tasks import process_bulk_queue
from oarepo_runtime import current_runtime

from oarepo_oaipmh_harvester.proxies import (
    current_oai_harvester_service,
    current_oai_record_service,
)
from oarepo_oaipmh_harvester.tasks import harvest_oaipmh_records


@pytest.fixture
def harvester(app, db, search_clear):
    harvester_data = {
        "id": "test",
        "name": "Test Harvester",
        "base_url": "https://zenodo.org/oai2d",
        "metadata_prefix": "oai_dc",
        "setspec": "",
        "loader": "oai-pmh",
        "transformers": ['oai-import{model:"test"}'],
        "writers": ['oai-service{model:"test",update:true}'],
        "harvest_managers": ["1"],
        "comment": "This is a test harvester.",
    }

    current_oai_harvester_service.create(system_identity, harvester_data)
    db.session.commit()
    return "test"


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
