#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Results for the oai_records service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from invenio_records_resources.services.records.results import RecordItem, RecordList

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask_principal import Identity
    from invenio_records_resources.services.base.links import LinksTemplate
    from invenio_records_resources.services.records.schema import ServiceSchemaWrapper

    from .api import OAIRecordAggregate
    from .service import OAIRecordService


class OAIRecordItem(RecordItem):
    """Single OAI Run result."""

    _data: dict | None

    def __init__(  # noqa: PLR0913 # too many arguments
        self,
        service: OAIRecordService,
        identity: Identity,
        oai_record: OAIRecordAggregate,
        errors: list[Any] | None = None,
        links_tpl: LinksTemplate | None = None,
        schema: ServiceSchemaWrapper | None = None,
        **_kwargs: Any,
    ):
        """Create OAIRecordItem."""
        self._data = None
        self._errors = errors
        self._identity = identity
        self._oai_record = oai_record
        self._service = service
        self._links_tpl = links_tpl
        self._schema = schema or service.schema

    @property
    def id(self) -> str:
        """Identity of the oai_record."""
        return str(self._oai_record.id)

    def __getitem__(self, key: str):
        """Key a key from the data."""
        return self.data[key]

    @property
    def links(self) -> dict[str, str]:
        """Get links for this result item."""
        if self._links_tpl:
            return self._links_tpl.expand(self._identity, self._oai_record)  # type: ignore[no-any-return]
        return {}

    @property
    def _obj(self) -> OAIRecordAggregate:
        """Return the object to dump."""
        return self._oai_record

    @property
    def data(self) -> dict[str, Any]:
        """Property to get the oai_record."""
        if self._data:
            return self._data

        self._data = self._schema.dump(
            self._obj,
            context={
                "identity": self._identity,
                "record": self._oai_record,
            },
        )

        if self._links_tpl:
            self._data["links"] = self.links

        return self._data

    @property
    def errors(self) -> list[Any] | None:
        """Get the errors."""
        return self._errors

    def to_dict(self) -> dict[str, Any]:
        """Get a dictionary for the oai_record."""
        res = self.data
        if self._errors:
            res["errors"] = self._errors
        return res


class OAIRecordList(RecordList):
    """List of OAI Run results."""

    @property
    @override
    def hits(self) -> Iterator[dict[str, Any]]:
        """Iterator over the hits."""
        oai_record_cls = self._service.record_cls

        for hit in self._results:
            # load dump
            oai_record = oai_record_cls.loads(hit.to_dict())
            schema = self._service.schema

            # project the oai_record
            projection = schema.dump(
                oai_record,
                context={
                    "identity": self._identity,
                    "record": oai_record,
                },
            )

            # inject the links
            if self._links_item_tpl:
                projection["links"] = self._links_item_tpl.expand(self._identity, oai_record)

            yield projection

    def to_dict(self) -> dict[str, Any]:
        """Return result as a dictionary."""
        # TODO: This part should imitate the result item above. I.e. add a
        # "data" property which uses a ServiceSchema to dump the entire object.
        res = {
            "hits": {
                "hits": list(self.hits),
                "total": self.total,
            }
        }

        if self.aggregations:
            res["aggregations"] = self.aggregations

        if self._params:
            res["sortBy"] = self._params["sort"]
            if self._links_tpl:
                res["links"] = self._links_tpl.expand(self._identity, self.pagination)

        return res
