#
# Copyright (c) 2026 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
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
