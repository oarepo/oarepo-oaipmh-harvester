#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Service layer for OAI-PMH Harvester."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast, override

from invenio_db import db
from invenio_db.uow import unit_of_work
from invenio_records_resources.services import (
    Link,
    RecordService,
    RecordServiceConfig,
    pagination_links,
)
from invenio_records_resources.services.base.config import (
    ConfiguratorMixin,
    FromConfig,
    SearchOptionsMixin,
)
from invenio_records_resources.services.errors import PermissionDeniedError
from invenio_records_resources.services.records.config import SearchOptions
from invenio_records_resources.services.records.params import (
    FacetsParam,
    PaginationParam,
    QueryStrParam,
    SortParam,
)
from invenio_records_resources.services.records.queryparser import (
    SuggestQueryParser,
)
from invenio_records_resources.services.uow import RecordCommitOp, RecordDeleteOp

from oarepo_oaipmh_harvester.links import ActionLinks

from ..permissions import OAIHarvesterPermissionPolicy
from . import facets
from .api import OAIHarvesterAggregate
from .models import OAIHarvester
from .results import OAIHarvesterItem, OAIHarvesterList
from .schema import OAIHarvesterSchema

if TYPE_CHECKING:
    from collections.abc import Mapping

    import marshmallow as ma
    from flask_principal import (
        Identity,
    )
    from invenio_db.uow import UnitOfWork
    from invenio_records_resources.services.records.results import (
        RecordItem,
        RecordList,
    )


log = logging.getLogger(__name__)


class OAIHarvesterSearchOptions(SearchOptions, SearchOptionsMixin):
    """Search options."""

    pagination_options: Mapping[str, Any] = {
        "default_results_per_page": 25,
        "default_max_results": 10000,
    }

    suggest_parser_cls = SuggestQueryParser.factory(  # type: ignore[assignment]  # passing partial instead of class
        fields=["comment^1", "name^2", "id^3"],
        type="most_fields",
        fuzziness="AUTO",
    )

    params_interpreters_cls = (
        QueryStrParam,
        SortParam,
        PaginationParam,
        FacetsParam,
    )

    facets: Mapping[str, Any] = {
        "base_url": facets.base_url,
        "name": facets.name,
        "metadata_prefix": facets.metadata_prefix,
        "setspec": facets.setspec,
        "loader": facets.loader,
        "transformers": facets.transformers,
        "writers": facets.writers,
        "harvest_managers": facets.harvest_managers,
    }


class RecordLink(Link):
    """Short cut for writing record links."""

    @staticmethod
    def vars(
        record: OAIHarvesterAggregate,
        vars: dict[str, Any],  # noqa ARG002
    ) -> None:
        """Variables for the URI template."""
        vars.update({"id": record.id})


class OAIHarvesterServiceConfig(RecordServiceConfig, ConfiguratorMixin):
    """Requests service configuration."""

    # common configuration
    permission_policy_cls = OAIHarvesterPermissionPolicy
    result_item_cls = OAIHarvesterItem
    result_list_cls = OAIHarvesterList

    search = OAIHarvesterSearchOptions

    service_id = "oai-harvester"
    record_cls = OAIHarvesterAggregate
    schema = cast("type[ma.Schema]", FromConfig("OAI_RECORD_SERVICE_SCHEMA", OAIHarvesterSchema))
    indexer_queue_name = "oai-harvester"
    index_dumper = None

    # links configuration
    links_item: Mapping[str, Any] = {
        "self": Link("{+api}/oai/harvest/harvester/{id}"),
        "actions": ActionLinks(
            {
                "harvest": RecordLink(
                    "{+api}/oai/harvest/harvester/{id}/harvest",
                ),
            }
        ),
    }
    links_search_item: Mapping[str, Any] = {
        "self": Link("{+api}/oai/harvest/harvester/{id}"),
        "actions": ActionLinks(
            {
                "harvest": RecordLink(
                    "{+api}/oai/harvest/harvester/{id}/harvest",
                ),
            }
        ),
    }
    links_search = pagination_links("{+api}/oai/harvest/harvester{?args*}")

    components = ()


class OAIHarvesterService(RecordService):
    """Harvester service."""

    @property
    def oai_harvester_cls(self) -> type[OAIHarvesterAggregate]:
        """Alias for record_cls."""
        return cast("type[OAIHarvesterAggregate]", self.record_cls)

    @override
    @unit_of_work()
    def create(
        self,
        identity: Identity,
        data: dict[str, Any],
        uow: UnitOfWork,
        expand: bool = False,
        raise_errors: bool = False,
    ) -> RecordItem:
        """Create a new OAI harvester."""
        # can not use super().create because it creates an empty record first
        # which is incompatible with our database constraints
        self.require_permission(identity, "create", data=data)

        # Validate data and create record with pid
        data, errors = self.schema.load(
            data,
            context={"identity": identity},
            raise_errors=raise_errors,  # if False, flow is continued with data
            # only containing valid data, but errors
            # are reported (as warnings)
        )

        record = self.record_cls.create(data, id_=data["id"])

        self.run_components(
            "create",
            identity,
            data=data,
            record=record,
            errors=errors,
            uow=uow,
        )

        # Persist record (DB and index)
        uow.register(RecordCommitOp(record, self.indexer, index_refresh=True))

        return self.result_item(
            self,
            identity,
            record,
            links_tpl=self.links_item_tpl,
            nested_links_item=getattr(self.config, "nested_links_item", None),
            errors=errors,
            expandable_fields=self.expandable_fields,
            expand=expand,
        )

    @override
    def search(
        self,
        identity: Identity,
        params: dict[str, Any] | None = None,
        search_preference: str | None = None,
        expand: bool = False,
        **kwargs: Any,
    ) -> RecordList:
        """Search for oai_records."""
        self.require_permission(identity, "search")

        return super().search(
            identity,
            params=params,
            search_preference=search_preference,
            search_opts=self.config.search,
            permission_action="read",
            **kwargs,
        )

    @override
    def read(self, identity: Identity, id_: str, expand: bool = False, action: str = "read") -> RecordItem:
        """Retrieve a oai_record."""
        # resolve and require permission
        oai_record = OAIHarvesterAggregate.get_record(id_)
        if oai_record is None:
            raise PermissionDeniedError

        self.require_permission(identity, "read", record=oai_record)

        # record components
        for component in self.components:
            if hasattr(component, "read"):
                component.read(identity, oai_record=oai_record)

        return self.result_item(self, identity, oai_record, links_tpl=self.links_item_tpl)

    @override
    @unit_of_work()
    def update(
        self,
        identity: Identity,
        id_: str,
        data: dict[str, Any],
        uow: UnitOfWork,
        revision_id: int | None = None,
        expand: bool = False,
        **kwargs: Any,
    ) -> RecordItem:
        """Replace a record."""
        record = OAIHarvesterAggregate.get_record(id_)

        # Permissions
        self.require_permission(identity, "update", record=record, data=data, **kwargs)

        data["id"] = record.id  # overwrite the id to prevent changing it
        data, _ = self.schema.load(data, context={"identity": identity, "record": record})

        # model fields can not use update method directly, we need to iterate and set attribute
        for key, value in data.items():
            if key != "id":
                setattr(record, key, value)

        uow.register(RecordCommitOp(record, self.indexer))

        return self.result_item(
            self,
            identity,
            record,
            links_tpl=self.links_item_tpl,
            nested_links_item=getattr(self.config, "nested_links_item", None),
            expandable_fields=self.expandable_fields,
            expand=expand,
        )

    @override
    @unit_of_work()
    def delete(
        self,
        identity: Identity,
        id_: str,
        uow: UnitOfWork,
        revision_id: int | None = None,
        **kwargs: Any,
    ) -> bool:
        """Delete a record from database and search indexes."""
        record = OAIHarvesterAggregate.get_record(id_)

        # Permissions
        self.require_permission(identity, "delete", record=record, **kwargs)

        uow.register(RecordDeleteOp(record, self.indexer, index_refresh=True, force=True))

        return True

    @override
    def rebuild_index(self, identity: Identity, uow: UnitOfWork | None = None) -> bool:
        """Reindex all oai_records managed by this service."""
        oai_harvesters = db.session.query(OAIHarvester.id).yield_per(1000)
        self.indexer.bulk_index([u.id for u in oai_harvesters])
        return True

    def harvest(self, identity: Identity, id_: str) -> RecordItem:
        """Re-harvest a oai_harvester."""
        # resolve and require permission
        oai_harvester = OAIHarvesterAggregate.get_record(id_)
        if oai_harvester is None:
            raise PermissionDeniedError

        self.require_permission(identity, "run_harvest", harvester=oai_harvester, record=oai_harvester)

        from ..tasks import harvest_oaipmh_records

        # Fire-and-forget: we do not need the result of the Celery task here.
        harvest_oaipmh_records.delay(oai_harvester.id)  # type: ignore[reportFunctionMemberAccess]

        return self.result_item(self, identity, oai_harvester, links_tpl=self.links_item_tpl)
