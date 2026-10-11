#
# Copyright (c) 2026 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""External (data provided) record pid, as used in NMA (riv.records)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from invenio_drafts_resources.records import Draft
from invenio_drafts_resources.records.api import DraftRecordIdProviderV2
from invenio_pidstore.models import PIDStatus
from invenio_records_resources.records.systemfields import PIDField
from invenio_records_resources.records.systemfields.pid_statuscheck import PIDStatusCheckField
from invenio_records_resources.services.records.components.base import ServiceComponent

if TYPE_CHECKING:
    from invenio_pidstore.models import PersistentIdentifier
    from invenio_records_resources.records.api import Record


class ExternalPIDProvider(DraftRecordIdProviderV2):
    """Pid provider taking the pid value from the record ``id``."""

    @classmethod
    def get_pid_value_from_record(cls, record_data: dict[str, Any]) -> str:
        """Get the pid value from (not yet created) record data - used by the oai writer."""
        return cls.generate_id({"record": record_data})

    @classmethod
    @override
    def generate_id(cls, options: dict[str, Any] | None = None) -> str:
        return (options or {})["record"]["id"]

    @classmethod
    @override
    def create(
        cls,
        object_type: str | None = None,
        object_uuid: str | None = None,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        options = {**(options or {}), "record": kwargs.pop("record")}
        return super().create(object_type=object_type, object_uuid=object_uuid, options=options, **kwargs)


class ExternalPIDFieldContextMixin:
    """Expose pid creation on the field context, used by ``ExternalPIDComponent``."""

    def create(self, record: Record) -> PersistentIdentifier:
        """Proxy to the field's create method."""
        return self.field.create(record)  # type: ignore[attr-defined]


class ExternalPIDField(PIDField):
    """Pid field that does not create the pid for drafts on its own - the component does."""

    @override
    def post_create(self, record: Record) -> None:
        if not isinstance(record, Draft) and self._provider and self._create:
            self.create(record)


class NoPIDStatusCheckField(PIDStatusCheckField):
    """Pid status check returning False while the draft has no pid yet (during create)."""

    @override
    def __get__(self, record: Record | None, owner: Any = None) -> Any:
        try:
            return super().__get__(record, owner)
        except AttributeError:
            return False


class NoPIDStatusCheckFieldMixin:
    """Draft mixin using ``NoPIDStatusCheckField`` for ``is_published``."""

    is_published = NoPIDStatusCheckField(status=PIDStatus.REGISTERED, dump=True)


class ExternalPIDComponent(ServiceComponent):
    """Create the draft pid from the ``id`` in the input data."""

    def create(self, identity: Any, data: dict | None = None, record: Record | None = None, **kwargs: Any) -> None:  # noqa: ARG002
        """Create pid when the record is created."""
        record["id"] = data["id"]  # type: ignore[index]
        self.service.draft_cls.pid.create(record)  # type: ignore[attr-defined]
