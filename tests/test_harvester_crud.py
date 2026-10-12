# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

from __future__ import annotations

import pytest
from invenio_access.permissions import system_identity
from invenio_pidstore.errors import PIDDoesNotExistError

from oarepo_oaipmh_harvester.proxies import current_oai_harvester_service


def test_harvester_crud(db, app, search, search_clear, user_with_administration_rights, client):
    harvester_data = {
        "id": "test",
        "name": "Test Harvester",
        "base_url": "http://example.com/oai",
        "metadata_prefix": "oai_dc",
        "setspec": "set1",
        "loader": "oai_dc_loader",
        "transformers": ["transformer1", "transformer2"],
        "writers": ["writer1"],
        "harvest_managers": [{"user": "1"}],
        "comment": "This is a test harvester.",
    }

    harvester = current_oai_harvester_service.create(system_identity, harvester_data)
    current_oai_harvester_service.indexer.refresh()

    created_harvester = harvester.to_dict()

    assert created_harvester["name"] == harvester_data["name"]
    assert created_harvester["base_url"] == harvester_data["base_url"]
    assert created_harvester["metadata_prefix"] == harvester_data["metadata_prefix"]
    assert created_harvester["setspec"] == harvester_data["setspec"]
    assert created_harvester["loader"] == harvester_data["loader"]
    assert created_harvester["transformers"] == harvester_data["transformers"]
    assert created_harvester["writers"] == harvester_data["writers"]
    assert created_harvester["harvest_managers"] == harvester_data["harvest_managers"]
    assert created_harvester["comment"] == harvester_data["comment"]

    # make sure we read the database version, not a cached one
    db.session.expunge_all()

    read_harvester = current_oai_harvester_service.read(system_identity, harvester.id)
    read_harvester_dict = read_harvester.to_dict()
    assert read_harvester_dict["id"] == harvester_data["id"]
    assert read_harvester_dict["name"] == created_harvester["name"]

    # use http client to read the harvester
    # we need to merge the user as expunge_all detached it and client depends on it
    user_with_administration_rights._user = db.session.merge(user_with_administration_rights.user)
    user_with_administration_rights.api_login(client)
    response = client.get(f"/api/oai/harvest/harvesters/{harvester.id}")
    assert response.status_code == 200
    response_data = response.get_json()
    assert response_data["id"] == harvester_data["id"]
    assert response_data["name"] == harvester_data["name"]
    assert response_data["base_url"] == harvester_data["base_url"]
    assert response_data["metadata_prefix"] == harvester_data["metadata_prefix"]
    assert response_data["setspec"] == harvester_data["setspec"]
    assert response_data["loader"] == harvester_data["loader"]
    assert response_data["transformers"] == harvester_data["transformers"]
    assert response_data["writers"] == harvester_data["writers"]
    assert response_data["harvest_managers"] == harvester_data["harvest_managers"]
    assert response_data["comment"] == harvester_data["comment"]

    found_harvesters = current_oai_harvester_service.search(system_identity, {"q": "Test"}).to_dict()
    assert found_harvesters["hits"]["total"] == 1
    assert found_harvesters["hits"]["hits"][0]["id"] == harvester_data["id"]

    response = client.get("/api/oai/harvest/harvesters/?q=Test")
    assert response.status_code == 200
    response_data = response.get_json()
    assert response_data["hits"]["total"] == 1
    assert response_data["hits"]["hits"][0]["id"] == harvester_data["id"]

    updated_data = {
        **read_harvester_dict,
        "name": "Updated Harvester",
        "comment": "This is an updated test harvester.",
    }
    updated_harvester = current_oai_harvester_service.update(system_identity, harvester.id, updated_data).to_dict()
    current_oai_harvester_service.indexer.refresh()
    assert updated_harvester["name"] == updated_data["name"]
    assert updated_harvester["comment"] == updated_data["comment"]

    response = client.put(
        f"/api/oai/harvest/harvesters/{harvester.id}",
        json={
            **updated_harvester,
            "name": "Updated Harvester via API",
            "comment": "This is an updated test harvester via API.",
        },
    )
    assert response.status_code == 200
    response_data = response.get_json()
    assert response_data["name"] == "Updated Harvester via API"
    assert response_data["comment"] == "This is an updated test harvester via API."

    # read again and check
    db.session.expunge_all()
    read_harvester = current_oai_harvester_service.read(system_identity, harvester.id)
    read_harvester_dict = read_harvester.to_dict()
    assert read_harvester_dict["name"] == "Updated Harvester via API"
    assert read_harvester_dict["comment"] == "This is an updated test harvester via API."

    current_oai_harvester_service.delete(system_identity, harvester.id)
    current_oai_harvester_service.indexer.refresh()

    with pytest.raises(PIDDoesNotExistError):
        current_oai_harvester_service.read(system_identity, harvester.id)


def test_admin_fields_exist_in_schema():
    """The admin form generator crashes on form fields missing in the resource schema."""
    from oarepo_oaipmh_harvester.administration.harvester.views import (
        OAIHarvesterFormMixin,
        OAIPMHDetailView,
        OAIPMHListView,
    )
    from oarepo_oaipmh_harvester.oai_harvester.schema import OAIHarvesterSchema

    schema_fields = set(OAIHarvesterSchema().fields)
    for fields in (OAIHarvesterFormMixin.form_fields, OAIPMHListView.item_field_list, OAIPMHDetailView.item_field_list):
        assert set(fields) <= schema_fields, set(fields) - schema_fields


def test_admin_form_text_round_trip(app, db, users):
    """The edit form gets newline separated text and saves it back."""
    from oarepo_oaipmh_harvester.oai_harvester.resource import AdministrationEditJSONSerializer
    from oarepo_oaipmh_harvester.oai_harvester.schema import OAIHarvesterSchema

    stored = {
        "transformers": ["oai-import{model:'datasets'}", "id-from-doi"],
        "writers": ['oai-service{"model": "datasets"}'],
        "harvest_managers": [{"user": str(users[0].id)}],
    }
    form = AdministrationEditJSONSerializer()._convert_to_form(stored)
    assert form["transformers"] == "oai-import{model:'datasets'}\nid-from-doi"
    assert form["harvest_managers"] == users[0].email

    from oarepo_oaipmh_harvester.oai_harvester.resource import AdministrationDetailJSONSerializer

    detail = AdministrationDetailJSONSerializer()._convert_to_administration_detail(stored)
    assert detail["harvest_managers"] == users[0].email

    loaded = OAIHarvesterSchema()._load_form_text({**form, "writers": form["writers"] + "\n\n"})
    assert loaded == stored
