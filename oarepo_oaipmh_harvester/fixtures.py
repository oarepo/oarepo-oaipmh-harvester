# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""``oai_harvesters`` fixture - harvesters loaded from ``app_data/oai_harvesters.yaml``.

Registered via the ``oarepo.fixtures`` entry point. Each YAML entry uses the keys of the
``invenio oai harvesters create`` command (``id``, ``name``, ``base-url``,
``metadata-prefix``, ``setspec``, ``loader``, ``model``, ``transformer``, ``writer``,
``harvest-manager``, ``comment``). Existing harvesters are updated.

When ``model`` is given and ``transformer`` / ``writer`` are not, the defaults are
``oai-import{model:...}`` and ``oai-service{model:...}``, as in the command line.

``harvest-manager`` entries are e-mail addresses of existing users (or ``{"user": id}``
dictionaries); they are stored as user ids.
"""

from __future__ import annotations

from typing import Any

from flask import current_app
from invenio_access.permissions import system_identity
from invenio_db import db
from invenio_rdm_records.fixtures.fixture import FixtureMixin

from oarepo_oaipmh_harvester.cli import lookup_user
from oarepo_oaipmh_harvester.proxies import current_oai_harvester_service


class HarvestersFixture(FixtureMixin):
    """Harvesters fixture."""

    def transform_data(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Transform the raw entry data into a harvester data dictionary."""
        transformers = list(entry.pop("transformer", []))
        writers = list(entry.pop("writer", []))
        model = entry.pop("model", None)

        if model:
            if not transformers:
                transformers = [f'oai-import{{model:"{model}"}}']
            if not writers:
                writers = [f'oai-service{{model:"{model}"}}']

        harvester_data = {
            "id": entry.pop("id"),
            "name": entry.pop("name"),
            "base_url": entry.pop("base-url"),
            "metadata_prefix": entry.pop("metadata-prefix"),
            "setspec": entry.pop("setspec", ""),
            "loader": entry.pop("loader", "oai-pmh"),
            "transformers": transformers,
            "writers": writers,
            "comment": entry.pop("comment", ""),
        }

        harvest_managers = [
            {"user": lookup_user(manager)} if isinstance(manager, str) else manager
            for manager in entry.pop("harvest-manager", [])
        ]
        if harvest_managers:
            harvester_data["harvest_managers"] = harvest_managers

        return harvester_data

    def create(self, entry: dict[str, Any]) -> None:
        """Create a new OAI-PMH harvester."""
        # Handle model option to auto-generate transformers and writers
        harvester_data = self.transform_data(entry)
        try:
            try:
                current_oai_harvester_service.create(system_identity, harvester_data)
            except Exception:  # noqa: BLE001
                db.session.rollback()
                current_oai_harvester_service.update(system_identity, harvester_data["id"], harvester_data)

            db.session.commit()
            current_oai_harvester_service.indexer.refresh()

            current_app.logger.info(
                "Harvester '%s' created successfully with ID: %s",
                harvester_data["name"],
                harvester_data["id"],
            )
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error creating harvester %s (transformed data: %s)", entry, harvester_data)
            raise
