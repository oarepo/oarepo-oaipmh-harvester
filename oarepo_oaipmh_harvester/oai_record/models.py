#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Models for OAI-PMH harvested records."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from invenio_db import db
from invenio_users_resources.records.models import AggregateMetadata
from sqlalchemy.dialects import postgresql
from sqlalchemy_utils.types import JSONType, UUIDType

from oarepo_oaipmh_harvester.oai_harvester.models import OAIHarvester

if TYPE_CHECKING:
    import datetime


class OAIHarvestedRecord(db.Model):
    """Metadata about a harvested record.

    Always contains the latest metadata of the record, no previous versions are stored.
    """

    __tablename__ = "oai_harvest_records"

    oai_identifier = db.Column(db.String(255), primary_key=True)
    """OAI identifier of the record."""

    record_type = db.Column(db.String(32), nullable=True)
    """Type of the record."""

    record_pid = db.Column(db.String(255), nullable=True)
    """Persistent identifier (Record.pid) of the record (local identifier).

    Note that this is not the database ID but the PID value.
    """

    datestamp = db.Column(db.DateTime, nullable=False)
    """Datestamp of the record."""

    harvested_at = db.Column(db.DateTime, nullable=False)
    """Time when the record was harvested."""

    deleted = db.Column(db.Boolean, default=False, nullable=False)
    """True if the record was deleted during the harvest."""

    has_errors = db.Column(db.Boolean, default=False, nullable=False)
    """True if the record has errors during the harvest."""

    has_warnings = db.Column(db.Boolean, default=False, nullable=False)
    """True if the record has warnings during the harvest."""

    errors = db.Column(
        db.JSON()
        .with_variant(
            postgresql.JSONB(none_as_null=True),
            "postgresql",
        )
        .with_variant(
            JSONType(),
            "sqlite",
        )
        .with_variant(
            JSONType(),
            "mysql",
        ),
        default=dict,
        nullable=False,
    )
    """Errors."""

    original_data = db.Column(
        db.JSON()
        .with_variant(
            postgresql.JSONB(none_as_null=True),
            "postgresql",
        )
        .with_variant(
            JSONType(),
            "sqlite",
        )
        .with_variant(
            JSONType(),
            "mysql",
        ),
        default=dict,
        nullable=False,
    )
    """Original data."""

    transformed_data = db.Column(
        db.JSON()
        .with_variant(
            postgresql.JSONB(none_as_null=True),
            "postgresql",
        )
        .with_variant(
            JSONType(),
            "sqlite",
        )
        .with_variant(
            JSONType(),
            "mysql",
        ),
        default=dict,
        nullable=False,
    )
    """Transformed data before they were stored into the target record."""

    harvester_id = db.Column(
        db.String(30),
        db.ForeignKey("oai_harvesters.id"),
        nullable=False,
    )
    """ID of the harvester that harvested this record."""

    harvester = db.relationship(OAIHarvester)

    job_run_id = db.Column(UUIDType(binary=False), nullable=True)
    """Run ID of the harvest run (from invenio-jobs)."""


class OAIRecordAggregateModel(AggregateMetadata):
    """OAI Run aggregate data model."""

    _model_obj: OAIHarvestedRecord | None

    # If you add properties here you likely also want to add a ModelField on
    # the UserAggregate API class.
    _properties = (
        "oai_identifier",
        "record_id",
        "datestamp",
        "harvested_at",
        "deleted",
        "has_errors",
        "has_warnings",
        "errors",
        "original_data",
        "transformed_data",
        "harvester_id",
        "harvester",
    )
    """Properties of this object that can be accessed."""

    _set_properties: tuple[str, ...] = ()
    """Properties of this object that can be set."""

    @property
    @override
    def model_obj(self) -> OAIHarvestedRecord:  # type: ignore[reportIncompatibleMethodOverride]
        """The actual model object behind this user aggregate."""
        if self._model_obj is None:
            id_ = (self._data or {}).get("id")
            with db.session.no_autoflush:
                self._model_obj = OAIHarvestedRecord.query.get(id_)
        if self._model_obj is None:
            raise ValueError("OAIHarvestedRecord not found")
        return self._model_obj

    @property
    def version_id(self) -> int:
        """Return the version ID of the record."""
        return 1

    @property
    def created(self) -> datetime.datetime:
        """Return the creation date of the record."""
        return self.datestamp  # type: ignore[no-any-return]

    @property
    def updated(self) -> datetime.datetime:
        """Return the last update date of the record."""
        return self.datestamp  # type: ignore[no-any-return]

    @property
    def id(self) -> str:
        """Return the ID of the record."""
        return self.oai_identifier  # type: ignore[no-any-return]
