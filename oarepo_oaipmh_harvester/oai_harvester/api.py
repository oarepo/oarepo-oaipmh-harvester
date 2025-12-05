#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Record API level classes for OAI-PMH Harvester."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from flask import current_app
from invenio_db import db
from invenio_pidstore.errors import PIDDoesNotExistError
from invenio_records.dumpers import SearchDumper
from invenio_records.dumpers.indexedat import IndexedAtDumperExt
from invenio_records.errors import MissingModelError
from invenio_records.signals import (
    after_record_delete,
    before_record_delete,
)
from invenio_records.systemfields import ModelField
from invenio_records_resources.records.systemfields import IndexField
from invenio_users_resources.records.api import BaseAggregate

from .models import OAIHarvester, OAIHarvesterAggregateModel

if TYPE_CHECKING:
    from uuid import UUID


class HarvesterDumper(SearchDumper):
    """Search dumper with configured extensions."""

    def __init__(
        self,
    ) -> None:
        """Initialize the dumper."""
        super().__init__(
            extensions=[
                IndexedAtDumperExt(),
            ],
            model_fields={
                "id": ("uuid", str),
            },
        )


# note: should we use aggregate here? Alternative is to create a custom class
# that would do better handling of the underlying model
class OAIHarvesterAggregate(BaseAggregate):
    """An aggregate of information about a user."""

    model: OAIHarvesterAggregateModel

    model_cls = OAIHarvesterAggregateModel  # type: ignore[reportAssignmentType]
    """The model class for the request."""

    dumper = HarvesterDumper()
    """Search dumper with configured extensions."""

    index = IndexField(
        "oai-harvester-oai-harvester-v1.0.0",
    )
    """The search engine index to use."""

    id = ModelField("id", dump_type=str)  # type: ignore[reportAssignmentType]
    """The code of the harvester."""

    base_url = ModelField("base_url", dump_type=str)
    """The base URL of the OAI-PMH service."""

    name = ModelField("name", dump_type=str)
    """The name of the harvester."""

    comment = ModelField("comment", dump_type=str)
    """Comment."""

    metadata_prefix = ModelField("metadata_prefix", dump_type=str)
    """The metadata prefix to harvest."""

    setspec = ModelField("setspec", dump_type=str)
    """The set specifications to harvest."""

    loader = ModelField("loader", dump_type=str)
    """The definition of the loader."""

    transformers = ModelField("transformers", dump_type=list)
    """The list of transformers."""

    writers = ModelField("writers", dump_type=list)
    """The list of writers."""

    harvest_managers = ModelField("harvest_managers", dump_type=list)
    """The list of harvest managers. Each item is a dict with 'user' key with user ID."""

    @classmethod
    @override
    def create(
        cls,
        data: dict,
        id_: UUID | None = None,
        **kwargs: Any,
    ) -> OAIHarvesterAggregate:
        """Create a new OAI harvester and store it in the database."""
        with db.session.begin_nested():
            record = OAIHarvester(**data)
            db.session.add(record)
            return cls.from_model(record)  # type: ignore[no-any-return]

    @override
    def delete(self, force: bool = False) -> OAIHarvesterAggregate:
        """Delete a record."""
        if self.model is None:
            raise MissingModelError

        with db.session.begin_nested():
            if self.send_signals:
                before_record_delete.send(
                    current_app._get_current_object(),  # type: ignore[attr-defined] # noqa SLF001
                    record=self,
                )

            # Run pre delete extensions
            for e in self._extensions:
                e.pre_delete(self, force=True)

            # the only change from super is the model.model_obj instead of model
            db.session.delete(self.model.model_obj)

        if self.send_signals:
            after_record_delete.send(
                current_app._get_current_object(),  # type: ignore[attr-defined] # noqa SLF001
                record=self,
            )

        # Run post delete extensions
        for e in self._extensions:
            e.post_delete(self, force=True)

        return self

    @classmethod
    def get_record(cls, _id: str) -> OAIHarvesterAggregate:  # type: ignore[reportIncompatibleMethodOverride]
        """Get the user via the specified ID."""
        with db.session.no_autoflush:
            record = OAIHarvester.query.get(_id)
            if record is None:
                raise PIDDoesNotExistError(cls.__name__, _id)
            return cls.from_model(record)  # type: ignore[no-any-return]
