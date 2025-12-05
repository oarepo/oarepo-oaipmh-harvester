#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""API for OAI harvested records."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, override

from invenio_db import db
from invenio_records.dumpers import SearchDumper
from invenio_records.dumpers.indexedat import IndexedAtDumperExt
from invenio_records.systemfields import ModelField
from invenio_records_resources.records.systemfields import IndexField
from invenio_users_resources.records.api import BaseAggregate

from .dumpers import AddHarvesterDumperExt
from .models import OAIHarvestedRecord, OAIRecordAggregateModel

if TYPE_CHECKING:
    from uuid import UUID


class OAIRecordAggregate(BaseAggregate):
    """An aggregate of information about a user."""

    model_cls = OAIRecordAggregateModel  # type: ignore[reportAssignmentType]
    """The model class for the request."""

    dumper = SearchDumper(
        extensions=[
            IndexedAtDumperExt(),
            AddHarvesterDumperExt(),
        ],
        model_fields={
            "id": ("uuid", str),
        },
    )
    """Search dumper with configured extensions."""

    index = IndexField(
        "oai-harvest-record-oai-harvest-record-v1.0.0",
        search_alias="oai-harvest-record",
    )
    """The search engine index to use."""

    oai_identifier = ModelField("oai_identifier", dump_type=str)
    """The OAI identifier of the record."""
    record_id = ModelField("record_id", dump_type=str)
    """The record ID of the record."""
    datestamp = ModelField("datestamp", dump_type=datetime)
    """The datestamp of the record."""
    harvested_at = ModelField("harvested_at", dump_type=datetime)
    """The time when the record was harvested."""
    deleted = ModelField("deleted", dump_type=bool)
    """True if the record was deleted during the harvest."""
    has_errors = ModelField("has_errors", dump_type=bool)
    """True if the record has errors during the harvest."""
    has_warnings = ModelField("has_warnings", dump_type=bool)
    """True if the record has warnings during the harvest."""
    errors = ModelField("errors", dump_type=list[dict])
    """Errors."""
    original_data = ModelField("original_data", dump_type=dict)
    """Original data."""
    transformed_data = ModelField("transformed_data", dump_type=dict)
    """Transformed data."""
    harvester_id = ModelField("harvester_id", dump_type=str)
    """The run ID of the record."""
    harvester = ModelField("harvester", dump=False)
    """The harvester of the record."""

    @classmethod
    @override
    def create(
        cls,
        data: dict[str, Any],
        id_: UUID | None = None,
        **kwargs: Any,
    ) -> OAIRecordAggregate:
        """Create a new User and store it in the database."""
        with db.session.begin_nested():
            record = OAIHarvestedRecord(**data)
            db.session.add(record)
            return cls.from_model(record)  # type: ignore[no-any-return]

    @classmethod
    @override
    def get_record(cls, id_: UUID | str, with_deleted: bool = False) -> OAIRecordAggregate:
        """Get the user via the specified ID."""
        with db.session.no_autoflush:
            record = OAIHarvestedRecord.query.get(id_)
            return cls.from_model(record)  # type: ignore[no-any-return]
