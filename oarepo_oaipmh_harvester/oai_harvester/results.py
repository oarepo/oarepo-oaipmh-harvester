#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Results for the oai_harvesters service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from invenio_records_resources.services.records.results import RecordItem, RecordList

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask_principal import Identity
    from invenio_records_resources.services.base.links import LinksTemplate
    from invenio_records_resources.services.records.schema import ServiceSchemaWrapper

    from .api import OAIHarvesterAggregate
    from .service import OAIHarvesterService


class OAIHarvesterItem(RecordItem):
    """Single OAI Harvester result."""

    _data: dict | None

    def __init__(  # noqa: PLR0913 # too many arguments
        self,
        service: OAIHarvesterService,
        identity: Identity,
        oai_harvester: OAIHarvesterAggregate,
        errors: list[Any] | None = None,
        links_tpl: LinksTemplate | None = None,
        schema: ServiceSchemaWrapper | None = None,
        **_kwargs: Any,
    ):
        """Create OAIHarvesterItem."""
        self._data = None
        self._errors = errors
        self._identity = identity
        self._oai_harvester = oai_harvester
        self._service = service
        self._links_tpl = links_tpl
        self._schema = schema or service.schema

    @property
    def id(self) -> str:
        """Identity of the oai_harvester."""
        return str(self._oai_harvester.id)

    def __getitem__(self, key: str) -> Any:
        """Key a key from the data."""
        return self.data[key]

    @property
    @override
    def links(self) -> dict[str, str]:
        """Get links for this result item."""
        if self._links_tpl:
            return self._links_tpl.expand(self._identity, self._oai_harvester)  # type: ignore[no-any-return]
        return {}

    @property
    @override
    def _obj(self) -> OAIHarvesterAggregate:
        """Return the object to dump."""
        return self._oai_harvester

    @property
    @override
    def data(self) -> dict[str, Any]:
        """Property to get the oai harvester."""
        if self._data:
            return self._data

        self._data = self._schema.dump(
            self._obj,
            context={
                "identity": self._identity,
                "harvester": self._oai_harvester,
            },
        )

        if self._links_tpl:
            self._data["links"] = self.links

        return self._data  # type: ignore[return-value]

    @property
    @override
    def errors(self) -> list[Any] | None:
        """Get the errors."""
        return self._errors

    @override
    def to_dict(self) -> dict[str, Any]:
        """Get a dictionary for the oai_harvester."""
        res = self.data
        if self._errors:
            res["errors"] = self._errors
        return res


class OAIHarvesterList(RecordList):
    """List of OAI Harvester results."""

    @property
    def hits(self) -> Iterator[dict[str, Any]]:
        """Iterator over the hits."""
        oai_harvester_cls = self._service.record_cls

        for hit in self._results:
            # load dump
            oai_harvester = oai_harvester_cls.loads(hit.to_dict())
            schema = self._service.schema

            # project the oai_harvester
            projection = schema.dump(
                oai_harvester,
                context={
                    "identity": self._identity,
                    "record": oai_harvester,
                },
            )

            # inject the links
            if self._links_item_tpl:
                projection["links"] = self._links_item_tpl.expand(self._identity, oai_harvester)

            yield projection

    def to_dict(self) -> dict:
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
