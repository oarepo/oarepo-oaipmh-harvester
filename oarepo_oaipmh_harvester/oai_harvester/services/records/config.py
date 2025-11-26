from invenio_records_resources.services import (
    LinksTemplate,
    RecordLink,
    pagination_links,
)
from invenio_records_resources.services import (
    RecordServiceConfig as InvenioRecordServiceConfig,
)
from invenio_records_resources.services.records.components import DataComponent

from oarepo_oaipmh_harvester.oai_harvester.records.api import OaiHarvesterRecord
from oarepo_oaipmh_harvester.oai_harvester.services.records.permissions import (
    OaiHarvesterPermissionPolicy,
)
from oarepo_oaipmh_harvester.oai_harvester.services.records.results import (
    OaiHarvesterRecordItem,
    OaiHarvesterRecordList,
)
from oarepo_oaipmh_harvester.oai_harvester.services.records.schema import (
    OaiHarvesterSchema,
)
from oarepo_oaipmh_harvester.oai_harvester.services.records.search import (
    OaiHarvesterSearchOptions,
)
from oarepo_oaipmh_harvester.services.links import ActionLinks


class OaiHarvesterServiceConfig(
    PermissionsPresetsConfigMixin, InvenioRecordServiceConfig
):
    """OaiHarvesterRecord service config."""

    result_item_cls = OaiHarvesterRecordItem

    result_list_cls = OaiHarvesterRecordList

    PERMISSIONS_PRESETS = ["oai_harvester"]

    url_prefix = "/oai/harvest/harvesters/"

    base_permission_policy_cls = OaiHarvesterPermissionPolicy

    schema = OaiHarvesterSchema

    search = OaiHarvesterSearchOptions

    record_cls = OaiHarvesterRecord

    service_id = "oarepo-oaipmh-harvesters"
    indexer_queue_name = "oarepo-oaipmh-harvesters"

    search_item_links_template = LinksTemplate

    @property
    def components(self):
        return process_service_configs(
            self, CachingRelationsComponent, DataComponent, CustomFieldsComponent
        )

    model = "oarepo_oaipmh_harvester.oai_harvester"

    links_search_item = {
        "actions": ActionLinks(
            {
                "harvest": RecordLink(
                    "{+api}/oai/harvest/harvesters/{id}/start",
                    when=has_permission("run_harvest"),
                ),
            }
        ),
        "self": RecordLink(
            "{+api}/oai/harvest/harvesters/{id}", when=has_permission("read")
        ),
        "self_html": RecordLink(
            "{+ui}/oai/harvest/harvesters/{id}", when=has_permission("read")
        ),
        "harvest": RecordLink(
            "{+api}/oai/harvest/harvesters/{id}/actions/harvest",
            when=has_permission("run_harvest"),
        ),
    }

    links_item = {
        "actions": ActionLinks(
            {
                "harvest": RecordLink(
                    "{+api}/oai/harvest/harvesters/{id}/actions/harvest",
                    when=has_permission("run_harvest"),
                ),
            }
        ),
        "self": RecordLink(
            "{+api}/oai/harvest/harvesters/{id}", when=has_permission("read")
        ),
        "self_html": RecordLink(
            "{+ui}/oai/harvest/harvesters/{id}", when=has_permission("read")
        ),
    }

    links_search = {
        **pagination_links("{+api}/oai/harvest/harvesters/{?args*}"),
        **pagination_links_html("{+ui}/oai/harvest/harvesters/{?args*}"),
    }
