# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Service for OAI-PMH harvested records."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast, override

from invenio_db import db
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
from invenio_records_resources.services.records.config import (
    SearchOptions,
)
from invenio_records_resources.services.records.params import (
    FacetsParam,
    PaginationParam,
    QueryStrParam,
    SortParam,
)
from invenio_records_resources.services.records.queryparser import (
    SuggestQueryParser,
)

from oarepo_oaipmh_harvester.links import ActionLinks

from ..permissions import OAIRecordPermissionPolicy
from . import facets
from .api import OAIRecordAggregate
from .models import OAIHarvestedRecord
from .results import OAIRecordItem, OAIRecordList
from .schema import OAIHarvestedRecordSchema

if TYPE_CHECKING:
    from collections.abc import Mapping

    import marshmallow as ma
    from flask_principal import Identity
    from invenio_db.uow import UnitOfWork
    from invenio_records_resources.services.records.results import (
        RecordItem,
        RecordList,
    )

log = logging.getLogger(__name__)


class OAIRecordSearchOptions(SearchOptions, SearchOptionsMixin):
    """Search options for harvest records."""

    pagination_options: Mapping[str, Any] = {
        "default_results_per_page": 25,
        "default_max_results": 10000,
    }

    suggest_parser_cls = SuggestQueryParser.factory(
        fields=["oai_identifier^2", "harvester_id^2", "title^3"],
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
        "harvester": facets.harvester,
        "deleted": facets.deleted,
        "has_errors": facets.has_errors,
        "error_code": facets.error_code,
        "error_message": facets.error_message,
        "error_location": facets.error_location,
    }


class RecordLink(Link):
    """Short cut for writing record links."""

    @staticmethod
    def vars(record: Any, link_vars: dict) -> None:
        """Variables for the URI template."""
        # Some records don't have record.pid.pid_value yet (e.g. drafts)
        link_vars.update({"id": record.id})


class OAIRecordServiceConfig(RecordServiceConfig, ConfiguratorMixin):
    """Harvest record service configuration."""

    # common configuration
    permission_policy_cls = OAIRecordPermissionPolicy
    result_item_cls = OAIRecordItem
    result_list_cls = OAIRecordList

    search = OAIRecordSearchOptions

    service_id = "oai-harvest-record"
    record_cls = OAIRecordAggregate
    schema = cast(
        "type[ma.Schema]",
        FromConfig("OAI_RECORD_SERVICE_SCHEMA", OAIHarvestedRecordSchema),
    )
    indexer_queue_name = "oai-harvest-record"
    index_dumper = None

    # links configuration
    links_item: Mapping[str, Any] = {
        "self": Link("{+api}/oai/harvest/records/{id}"),
        "actions": ActionLinks(
            {
                "harvest": RecordLink(
                    "{+api}/oai/harvest/records/{id}/harvest",
                ),
            }
        ),
    }
    links_search_item: Mapping[str, Any] = {
        "self": Link("{+api}/oai/harvest/records/{id}"),
        "actions": ActionLinks(
            {
                "harvest": RecordLink(
                    "{+api}/oai/harvest/records/{id}/harvest",
                ),
            }
        ),
    }
    links_search = pagination_links("{+api}/oai/harvest/records{?args*}")

    components = ()


class OAIRecordService(RecordService):
    """Service for harvested OAI-PMH records."""

    @property
    def oai_record_cls(self) -> type[OAIRecordAggregate]:
        """Alias for record_cls."""
        return cast("type[OAIRecordAggregate]", self.record_cls)

    @override
    def search(
        self,
        identity: Identity,
        params: dict[str, Any] | None = None,
        search_preference: str | None = None,
        expand: bool = False,
        **kwargs: Any,
    ) -> RecordList:
        """Search harvest records."""
        self.require_permission(identity, "search")

        return super().search(
            identity,
            params=params,
            search_preference=search_preference,
            search_opts=self.config.search,
            permission_action="read",
            expand=expand,
            **kwargs,
        )

    @override
    def read(
        self,
        identity: Identity,
        id_: str,
        expand: bool = False,
        action: str = "read",
        **kwargs: Any,
    ) -> RecordItem:
        """Retrieve a single harvest record."""
        # resolve and require permission
        oai_record = OAIRecordAggregate.get_record(id_)
        if oai_record is None:
            raise PermissionDeniedError

        self.require_permission(identity, "read", record=oai_record)

        # record components
        for component in self.components:
            if hasattr(component, "read"):
                component.read(identity, oai_record=oai_record)

        return self.result_item(self, identity, oai_record, links_tpl=self.links_item_tpl)

    @override
    def rebuild_index(self, identity: Identity, uow: UnitOfWork | None = None) -> bool:
        """Reindex all harvest records."""
        oai_records = db.session.query(OAIHarvestedRecord.oai_identifier).yield_per(1000)
        self.indexer.bulk_index([u.oai_identifier for u in oai_records])
        return True

    def harvest(self, identity: Identity, id_: str) -> RecordItem:
        """Re-harvest a single record from its source."""
        # resolve and require permission
        oai_record = OAIRecordAggregate.get_record(id_)
        if oai_record is None:
            raise PermissionDeniedError

        self.require_permission(identity, "run_harvest", record=oai_record)

        from ..tasks import harvest_oaipmh_records

        # Fire-and-forget: we do not need the result of the Celery task here.
        harvest_oaipmh_records.delay(harvester_id=oai_record.harvester.id, oai_ids=[id_])

        # re-get the record
        oai_record = OAIRecordAggregate.get_record(id_)

        return self.result_item(self, identity, oai_record, links_tpl=self.links_item_tpl)
