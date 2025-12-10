#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Database models for OAI-PMH harvester metadata."""

from __future__ import annotations

from invenio_db import db
from invenio_records.models import Timestamp
from invenio_users_resources.records.models import AggregateMetadata
from sqlalchemy_utils.types import JSONType


class OAIHarvester(db.Model, Timestamp):
    """Metadata about an OAI-PMH harvester."""

    __tablename__ = "oai_harvesters"

    id = db.Column(db.String(30), primary_key=True)
    """ID of the harvester."""

    base_url = db.Column(db.String(255), nullable=False)
    """The base URL of the OAI-PMH service."""

    name = db.Column(db.String(255), nullable=False)
    """The name of the harvester."""

    comment = db.Column(db.Text, nullable=True)
    """Comment."""

    metadata_prefix = db.Column(db.String(64), nullable=False)
    """The metadata prefix to harvest."""

    setspec = db.Column(db.String(255), nullable=True)
    """The set specifications to harvest."""

    loader = db.Column(db.String(255), nullable=False)
    """The definition of the loader."""

    transformers = db.Column(
        JSONType(),
        default=list,
        nullable=False,
    )
    """The list of transformers."""

    writers = db.Column(
        JSONType(),
        default=list,
        nullable=False,
    )
    """The list of writers."""

    harvest_managers = db.Column(
        JSONType(),
        default=list,
        nullable=False,
    )
    """The list of harvest managers. An array of {"user": user_id} dicts."""


class OAIHarvesterAggregateModel(AggregateMetadata):
    """OAI Run aggregate data model."""

    _model_obj: OAIHarvester | None

    # If you add properties here you likely also want to add a ModelField on
    # the UserAggregate API class.
    _properties = (
        "id",
        "base_url",
        "name",
        "comment",
        "metadata_prefix",
        "setspec",
        "loader",
        "transformers",
        "writers",
        "harvest_managers",
        "created",
        "updated",
    )
    """Properties of this object that can be accessed."""

    _set_properties = (
        "base_url",
        "name",
        "comment",
        "metadata_prefix",
        "setspec",
        "loader",
        "transformers",
        "writers",
        "harvest_managers",
    )
    """Properties of this object that can be set."""

    @property
    def model_obj(self) -> OAIHarvester:  # type: ignore[reportIncompatibleMethodOverride]
        """The actual model object behind this user aggregate."""
        if self._model_obj is None:
            _id = (self._data or {}).get("id")
            with db.session.no_autoflush:
                self._model_obj = OAIHarvester.query.get(_id)
        if self._model_obj is None:
            raise ValueError("OAIHarvester not found")  # pragma: no cover
        return self._model_obj

    @property
    def version_id(self) -> int:
        """Return the version ID of the record."""
        return 1
