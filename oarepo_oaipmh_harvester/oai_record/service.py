import logging

from invenio_db import db
from invenio_records_resources.resources.errors import PermissionDeniedError
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
from invenio_records_resources.services.errors import (
    PermissionDeniedError,
)
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
from invenio_users_resources.services.common import Link

from oarepo_oaipmh_harvester.oai_run.models import OAIHarvesterRun
from oarepo_oaipmh_harvester.proxies import current_oai_record_service
from oarepo_oaipmh_harvester.services.links import ActionLinks

from ..harvester import harvest
from ..models import OAIHarvestedRecord, OAIHarvesterRun
from ..permissions import OAIRecordPermissionPolicy
from . import facets
from .api import OAIRecordAggregate
from .results import OAIRecordItem, OAIRecordList
from .schema import OAIHarvestedRecordSchema

log = logging.getLogger(__name__)


class OAIRecordSearchOptions(SearchOptions, SearchOptionsMixin):
    """Search options."""

    pagination_options = {
        "default_results_per_page": 25,
        "default_max_results": 10000,
    }

    suggest_parser_cls = SuggestQueryParser.factory(
        fields=["oai_identifier^2", "harvester_id^2", "title^3"],
        type="most_fields",
        fuzziness="AUTO",
    )

    params_interpreters_cls = [
        QueryStrParam,
        SortParam,
        PaginationParam,
        FacetsParam,
    ]

    facets = {
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
    def vars(record, vars):
        """Variables for the URI template."""
        # Some records don't have record.pid.pid_value yet (e.g. drafts)
        vars.update({"id": record.id})


class has_permission_on_record(Condition):
    def __init__(self, action_name):
        self.action_name = action_name

    def __call__(self, obj, ctx: dict):
        try:
            return current_oai_record_service.check_permission(
                action_name=self.action_name, record=obj, **ctx
            )
        except Exception as e:
            log.exception(f"Unexpected exception {e}.")


class OAIRecordServiceConfig(RecordServiceConfig, ConfiguratorMixin):
    """Requests service configuration."""

    # common configuration
    permission_policy_cls = OAIRecordPermissionPolicy
    result_item_cls = OAIRecordItem
    result_list_cls = OAIRecordList

    search = OAIRecordSearchOptions

    service_id = "oai-harvest-record"
    record_cls = OAIRecordAggregate
    schema = FromConfig("OAI_RECORD_SERVICE_SCHEMA", OAIHarvestedRecordSchema)
    indexer_queue_name = "oai-harvest-record"
    index_dumper = None

    # links configuration
    links_item = {
        "self": Link("{+api}/oai/harvest/records/{id}"),
        "actions": ActionLinks(
            {
                "harvest": RecordLink(
                    "{+api}/oai/harvest/records/{id}/harvest",
                    when=has_permission_on_record("run_harvest"),
                ),
            }
        ),
    }
    links_search_item = {
        "self": Link("{+api}/oai/harvest/records/{id}"),
        "actions": ActionLinks(
            {
                "harvest": RecordLink(
                    "{+api}/oai/harvest/records/{id}/harvest",
                    when=has_permission_on_record("run_harvest"),
                ),
            }
        ),
    }
    links_search = pagination_links("{+api}/oai/harvest/records{?args*}")

    components = []


class OAIRecordService(RecordService):
    """Users service."""

    @property
    def oai_record_cls(self):
        """Alias for record_cls."""
        return self.record_cls

    def search(
        self,
        identity,
        params=None,
        search_preference=None,
        extra_filters=None,
        **kwargs,
    ):
        """Search for oai_records."""
        self.require_permission(identity, "search")

        return super().search(
            identity,
            params=params,
            search_preference=search_preference,
            search_opts=self.config.search,
            permission_action="read",
            extra_filter=extra_filters,
            **kwargs,
        )

    def read(self, identity, id_):
        """Retrieve a oai_record."""
        # resolve and require permission
        oai_record = OAIRecordAggregate.get_record(id_)
        if oai_record is None:
            raise PermissionDeniedError()

        self.require_permission(identity, "read", record=oai_record)

        # record components
        for component in self.components:
            if hasattr(component, "read"):
                component.read(identity, oai_record=oai_record)

        return self.result_item(
            self, identity, oai_record, links_tpl=self.links_item_tpl
        )

    def rebuild_index(self, identity, uow=None):
        """Reindex all oai_records managed by this service."""
        oai_records = db.session.query(OAIHarvestedRecord.id).yield_per(1000)
        self.indexer.bulk_index([u.id for u in oai_records])
        return True

    def harvest(self, identity, id_):
        """Re-harvest a oai_record."""
        # resolve and require permission
        oai_record = OAIRecordAggregate.get_record(id_)
        if oai_record is None:
            raise PermissionDeniedError()

        self.require_permission(identity, "run_harvest", record=oai_record)

        # run harvest with the oai identifier and correct harvester
        oai_run = OAIHarvesterRun.query.get(oai_record.run_id)

        callback = StatsKeepingDataStreamCallback(log_error_entry=True)

        harvest(
            harvester_or_code=oai_run.harvester_id,
            identifiers=[oai_record.oai_identifier],
            overwrite_all_records=True,
            manual=True,
            callback=callback,
        )

        # re-get the record
        oai_record = OAIRecordAggregate.get_record(id_)

        return self.result_item(
            self, identity, oai_record, links_tpl=self.links_item_tpl
        )
