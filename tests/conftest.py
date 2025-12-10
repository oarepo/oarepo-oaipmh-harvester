#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
from __future__ import annotations

from typing import Any, ClassVar

import pytest
from flask import current_app
from flask_resources.deserializers import DeserializerMixin
from invenio_access.models import ActionUsers
from invenio_app.factory import create_app as _create_app
from lxml import etree
from oarepo_model.api import model
from oarepo_model.customizations import AddMetadataImport
from oarepo_model.presets.records_resources import records_resources_preset

RawEntry = tuple[str | None, str]
LocalizedEntry = dict[str, str]

pytest_plugins = [
    "pytest_oarepo.ui.fixtures",
    "pytest_oarepo.fixtures",
    "pytest_oarepo.users",
]


class OAIDeserializer(DeserializerMixin):
    """OAI Dublin Core deserializer."""

    FIELD_SPECS: ClassVar[dict[str, dict[str, bool]]] = {
        "identifier": {"repeatable": True, "use_language": False},
        "title": {"repeatable": False, "use_language": True},
        "creator": {"repeatable": True, "use_language": False},
        "contributor": {"repeatable": True, "use_language": False},
        "rights": {"repeatable": True, "use_language": False},
        "date": {"repeatable": True, "use_language": False},
        "publisher": {"repeatable": True, "use_language": False},
        "language": {"repeatable": True, "use_language": False},
        "type": {"repeatable": True, "use_language": False},
        "subject": {"repeatable": True, "use_language": True},
        "description": {"repeatable": True, "use_language": True},
        "relation": {"repeatable": True, "use_language": False},
        "format": {"repeatable": True, "use_language": False},
    }

    def deserialize(self, raw_data: str) -> dict[str, Any]:
        """Deserialize raw OAI Dublin Core XML data into a dict."""
        from lxml import etree

        root = etree.fromstring(raw_data.encode("utf-8"))

        return self.deserialize_xml(root)

    def deserialize_xml(self, root: etree._Element) -> dict[str, Any]:
        """Deserialize OAI Dublin Core from an XML element."""
        metadata: dict[str, list[RawEntry]] = {}
        for elem in root:
            tag = etree.QName(elem).localname
            if tag not in metadata:
                metadata[tag] = []
            metadata[tag].append(
                (elem.get("{http://www.w3.org/XML/1998/namespace}lang"), elem.text)
            )

        metadata = self.process_metadata(metadata)
        return {
            "metadata": metadata,
            "files": {"enabled": False},  # TODO: need to move it somewhere else
        }

    def process_metadata(self, metadata: dict[str, list[RawEntry]]) -> dict[str, Any]:
        """Process the raw metadata dictionary to fit the model structure."""
        processed: dict[str, Any] = {}
        for field, entries in metadata.items():
            if field not in self.FIELD_SPECS:
                current_app.logger.warning("Unknown OAI DC field: %s, skipping.", field)
                continue
            normalized = self._normalize_entries(entries)
            if not normalized:
                continue
            spec = self.FIELD_SPECS[field]
            if not spec["repeatable"] and len(normalized) > 1:
                raise ValueError(
                    f"dc:{field} is not repeatable but {len(normalized)} instances were provided."
                )
            processed[field] = self._convert_entries(normalized, spec)
        return processed

    def _normalize_entries(self, entries: list[RawEntry]) -> list[RawEntry]:
        normalized: list[RawEntry] = []
        for lang, value in entries:
            if value is None:
                continue
            cleaned = value.strip()
            if not cleaned:
                continue
            normalized.append((lang, cleaned))
        return normalized

    def _convert_entries(
        self,
        entries: list[RawEntry],
        spec: dict[str, bool],
    ) -> list[str] | list[LocalizedEntry] | str | LocalizedEntry:
        if spec["repeatable"]:
            if spec["use_language"]:
                return [self._build_localized(lang, value) for lang, value in entries]
            return [value for _, value in entries]
        lang, value = entries[0]
        if spec["use_language"]:
            return self._build_localized(lang, value)
        return value

    def _build_localized(self, lang: str | None, value: str) -> LocalizedEntry:
        entry: LocalizedEntry = {"value": value}
        if lang:
            entry["lang"] = lang
        return entry


_test_model = model(
    "test",
    presets=[records_resources_preset],  # , oai_preset]
    types=[
        {
            "Metadata": {
                "type": "object",
                "properties": {
                    "identifier": {
                        "type": "array",
                        "items": {"type": "keyword"},
                    },
                    "title": {"type": "i18n"},
                    "creator": {
                        "type": "array",
                        "items": {"type": "fulltext+keyword"},
                    },
                    "contributor": {
                        "type": "array",
                        "items": {"type": "fulltext+keyword"},
                    },
                    "rights": {
                        "type": "array",
                        "items": {"type": "keyword"},
                    },
                    "date": {
                        "type": "array",
                        "items": {"type": "keyword"},
                    },
                    "publisher": {
                        "type": "array",
                        "items": {"type": "fulltext+keyword"},
                    },
                    "language": {
                        "type": "array",
                        "items": {"type": "keyword"},
                    },
                    "type": {
                        "type": "array",
                        "items": {"type": "keyword"},
                    },
                    "subject": {"type": "array", "items": {"type": "i18n"}},
                    "description": {"type": "array", "items": {"type": "i18n"}},
                    "relation": {
                        "type": "array",
                        "items": {"type": "keyword"},
                    },
                    "format": {
                        "type": "array",
                        "items": {"type": "keyword"},
                    },
                },
            }
        }
    ],
    metadata_type="Metadata",
    customizations=[
        AddMetadataImport(
            code="oai-dc",
            name="OAI Dublin Core",
            mimetype="application/oai-dc+xml",
            deserializer=OAIDeserializer(),
            description="Import from OAI Dublin Core format",
            oai_name=("http://www.openarchives.org/OAI/2.0/oai_dc/", "dc"),
        )
    ],
)
_test_model.register()


@pytest.fixture(scope="session", autouse=True)
def test_model():
    return _test_model


@pytest.fixture(scope="module")
def app_config(app_config, test_model):
    app_config["RECORDS_REFRESOLVER_CLS"] = (
        "invenio_records.resolver.InvenioRefResolver"
    )
    app_config["RECORDS_REFRESOLVER_STORE"] = (
        "invenio_jsonschemas.proxies.current_refresolver_store"
    )
    app_config["CELERY_TASK_ALWAYS_EAGER"] = True
    # disable session protection for tests to avoid issues with Flask-Login
    app_config["SESSION_PROTECTION"] = None
    return app_config


@pytest.fixture(scope="module")
def create_app(instance_path, entry_points):
    """Application factory fixture."""
    return _create_app


@pytest.fixture
def user_with_administration_rights(app, db, users):
    """Set administration rights to the first user and return it."""
    user = users[0]
    actions = app.extensions["invenio-access"].actions
    act = ActionUsers.allow(actions["administration-access"], user_id=user.user.id)
    db.session.add(act)
    db.session.commit()
    yield user
    db.session.delete(act)
    db.session.commit()
