# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""The `oai_harvesters` fixture - entries of `oai_harvesters.yaml` become harvesters."""

from __future__ import annotations

import pytest
from invenio_access.permissions import system_identity

from oarepo_oaipmh_harvester.fixtures import HarvestersFixture
from oarepo_oaipmh_harvester.proxies import current_oai_harvester_service


def _load(**options) -> dict:
    """Load one fixture entry with the given options, return the harvester it made."""
    HarvestersFixture(search_paths=[], filename="oai_harvesters.yaml").create(
        {
            "id": "fixture",
            "name": "Fixture harvester",
            "base-url": "https://example.org/oai",
            "metadata-prefix": "oai_dc",
            **options,
        }
    )
    return current_oai_harvester_service.read(system_identity, "fixture").to_dict()


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        pytest.param(
            {"model": "test"},
            {"transformers": ['oai-import{model:"test"}'], "writers": ['oai-service{model:"test"}']},
            id="defaults-for-the-model",
        ),
        pytest.param(
            {"model": "test", "community": "my-community"},
            {"writers": ['oai-service{"model": "test", "community": "my-community"}']},
            id="community-in-the-default-writer",
        ),
        pytest.param(
            {"writer": ['oai-service{model:"test",publish:false}', "other"], "community": "my-community"},
            {"writers": ['oai-service{"model": "test", "publish": false, "community": "my-community"}', "other"]},
            id="community-only-in-oai-service-writers",
        ),
    ],
)
def test_harvesters_fixture(app, db, search_clear, options, expected):
    harvester = _load(**options)

    assert {key: harvester[key] for key in expected} == expected


def test_harvest_managers_are_given_by_email(app, db, search_clear, users):
    harvester = _load(model="test", **{"harvest-manager": [users[0].email]})

    assert harvester["harvest_managers"] == [{"user": str(users[0].id)}]
