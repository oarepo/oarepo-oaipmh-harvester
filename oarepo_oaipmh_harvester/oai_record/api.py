# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

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

from .dumpers import AddHarvesterDumperExt, ErrorsFacetDumperExt
from .models import OAIHarvestedRecord, OAIRecordAggregateModel

if TYPE_CHECKING:
    from uuid import UUID


class OAIRecordAggregate(BaseAggregate):
    """An aggregate of information about a harvested record."""

    model_cls = OAIRecordAggregateModel  # ty: ignore[invalid-assignment] monkeytype
    """The model class for the request."""

    dumper = SearchDumper(
        extensions=[
            IndexedAtDumperExt(),
            AddHarvesterDumperExt(),
            ErrorsFacetDumperExt(),
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
    record_pid = ModelField("record_pid", dump_type=str)
    """The persistent identifier of the record."""
    datestamp = ModelField("datestamp", dump_type=datetime)
    """The OAI datestamp of the record."""
    harvested_at = ModelField("harvested_at", dump_type=datetime)
    """The time when the record was harvested."""
    deleted = ModelField("deleted", dump_type=bool)
    """True if the record was deleted during the harvest."""
    has_errors = ModelField("has_errors", dump_type=bool)
    """True if the record has errors during the harvest."""
    has_warnings = ModelField("has_warnings", dump_type=bool)
    """True if the record has warnings during the harvest."""
    errors = ModelField("errors", dump_type=list[dict])
    """Errors from the last write of the local record."""
    original_data = ModelField("original_data", dump_type=dict)
    """Original data as harvested from the OAI-PMH source."""
    transformed_data = ModelField("transformed_data", dump_type=dict)
    """Data after transformation, as written to the local record."""
    harvester_id = ModelField("harvester_id", dump_type=str)
    """ID of the harvester that harvested the record."""
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
        """Create a new harvested record and store it in the database."""
        with db.session.begin_nested():
            record = OAIHarvestedRecord(**data)
            db.session.add(record)
            return cls.from_model(record)

    @classmethod
    @override
    def get_record(cls, id_: UUID | str, with_deleted: bool = False) -> OAIRecordAggregate:
        """Get the harvested record with the specified ID."""
        with db.session.no_autoflush:
            record = OAIHarvestedRecord.query.get(id_)
            return cls.from_model(record)
