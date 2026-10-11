# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

from __future__ import annotations

from invenio_access.permissions import system_identity

from oarepo_oaipmh_harvester.fixtures import HarvestersFixture
from oarepo_oaipmh_harvester.proxies import current_oai_harvester_service


def test_harvesters_fixture(app, db, search_clear, users):
    fixture = HarvestersFixture(search_paths=[], filename="oai_harvesters.yaml")
    fixture.create(
        {
            "id": "fixture",
            "name": "Fixture harvester",
            "base-url": "https://example.org/oai",
            "metadata-prefix": "oai_dc",
            "model": "test",
            "harvest-manager": [users[0].email],
        }
    )

    harvester = current_oai_harvester_service.read(system_identity, "fixture").to_dict()
    assert harvester["transformers"] == ['oai-import{model:"test"}']
    assert harvester["writers"] == ['oai-service{model:"test"}']
    assert harvester["harvest_managers"] == [{"user": str(users[0].id)}]
