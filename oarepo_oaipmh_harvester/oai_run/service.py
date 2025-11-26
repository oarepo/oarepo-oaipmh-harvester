import logging

from invenio_db import db
from invenio_i18n import lazy_gettext as _
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
from oarepo_oaipmh_harvester.services.links import ActionLinks

from ..models import OAIHarvesterRun
from ..permissions import OAIRunPermissionPolicy
from . import facets
from .api import OAIRunAggregate
from .results import OAIRunItem, OAIRunList
from .schema import OAIHarvesterRunSchema

log = logging.getLogger(__name__)

from marshmallow import ValidationError

from oarepo_oaipmh_harvester.proxies import current_oai_run_service


class OAIRunSearchOptions(SearchOptions, SearchOptionsMixin):
    """Search options."""

    pagination_options = {
        "default_results_per_page": 25,
        "default_max_results": 10000,
    }

    suggest_parser_cls = SuggestQueryParser.factory(
        fields=["id^2", "harvester_id^2", "title^3"],
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
        "manual": facets.manual,
        "status": facets.status,
        "harvester_name": facets.harvester_name,
    }


class has_permission_on_run(Condition):
    def __init__(self, action_name):
        self.action_name = action_name

    def __call__(self, obj, ctx: dict):
        try:
            return current_oai_run_service.check_permission(
                action_name=self.action_name, record=obj, **ctx
            )
        except Exception as e:
            log.exception(f"Unexpected exception {e}.")


class RunLink(Link):
    """Short cut for writing record links."""

    @staticmethod
    def vars(record, vars):
        """Variables for the URI template."""
        # Some records don't have record.pid.pid_value yet (e.g. drafts)
        vars.update({"id": record.id})


class OAIRunServiceConfig(RecordServiceConfig, ConfiguratorMixin):
    """Requests service configuration."""

    # common configuration
    permission_policy_cls = OAIRunPermissionPolicy
    result_item_cls = OAIRunItem
    result_list_cls = OAIRunList

    search = OAIRunSearchOptions

    service_id = "oai-harvest-run"
    record_cls = OAIRunAggregate
    schema = FromConfig("OAI_RUN_SERVICE_SCHEMA", OAIHarvesterRunSchema)
    indexer_queue_name = "oai-harvest-run"
    index_dumper = None

    # links configuration
    links_item = {
        "self": Link("{+api}/oai/harvest/runs/{id}"),
        "actions": ActionLinks(
            {
                "stop": RunLink(
                    "{+api}/oai/harvest/runs/{id}/stop",
                    when=has_permission_on_run("stop_harvest"),
                ),
            }
        ),
    }
    links_search_item = {
        "self": Link("{+api}/oai/harvest/runs/{id}"),
        "actions": ActionLinks(
            {
                "stop": RunLink(
                    "{+api}/oai/harvest/runs/{id}/stop",
                    when=has_permission_on_run("stop_harvest"),
                ),
            }
        ),
    }
    links_search = pagination_links("{+api}/oai/harvest/runs{?args*}")

    components = []


class OAIRunService(RecordService):
    """Users service."""

    @property
    def oai_run_cls(self):
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
        """Search for oai_runs."""
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
        """Retrieve a oai_run."""
        # resolve and require permission
        oai_run = OAIRunAggregate.get_record(id_)
        if oai_run is None:
            raise PermissionDeniedError()

        self.require_permission(identity, "read", record=oai_run)

        # run components
        for component in self.components:
            if hasattr(component, "read"):
                component.read(identity, oai_run=oai_run)

        return self.result_item(self, identity, oai_run, links_tpl=self.links_item_tpl)

    def rebuild_index(self, identity, uow=None):
        """Reindex all oai_runs managed by this service."""
        oai_runs = db.session.query(OAIHarvesterRun.id).yield_per(1000)
        self.indexer.bulk_index([u.id for u in oai_runs])
        return True

    def stop(self, identity, id_):
        """Stop a running oai_run."""
        # resolve and require permission
        oai_run = OAIRunAggregate.get_record(id_)
        if oai_run is None:
            raise PermissionDeniedError()

        self.require_permission(identity, "stop_harvest", record=oai_run)
        if oai_run.status != "running":
            raise ValidationError(_("Cannot stop already stopped harvest run."))
        oai_run.status = "stopped"
        oai_run.commit()
        db.session.commit()
        return self.result_item(self, identity, oai_run, links_tpl=self.links_item_tpl)
