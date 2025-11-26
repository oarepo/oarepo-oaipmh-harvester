import importlib.metadata

from flask_resources.serializers.json import JSONSerializer
from invenio_i18n import lazy_gettext as _
from invenio_records_resources.resources import RecordResourceConfig
from invenio_records_resources.resources.records.headers import etag_headers

from oarepo_oaipmh_harvester.oai_harvester.resources.records.ui import (
    OaiHarvesterUIJSONSerializer,
)


class OaiHarvesterResourceConfig(RecordResourceConfig):
    """OaiHarvesterRecord resource config."""

    blueprint_name = "oarepo-oaipmh-harvester"
    url_prefix = "/oai/harvest/harvesters/"

    api_service = "oarepo-oaipmh-harvesters"
    routes = {
        "list": "",
        "item": "/<pid_value>",
        "harvest": "/<pid_value>/start",
    }

    @property
    def response_handlers(self):
        entrypoint_response_handlers = {}
        for x in importlib.metadata.entry_points(
            group="invenio.oarepo_oaipmh_harvester.oai_harvester.response_handlers"
        ):
            entrypoint_response_handlers.update(x.load())
        return {
            "application/json": ExportableResponseHandler(
                export_code="json",
                name=_("Native JSON"),
                serializer=JSONSerializer(),
                headers=etag_headers,
            ),
            "application/vnd.inveniordm.v1+json": ExportableResponseHandler(
                export_code="ui_json",
                name=_("Native UI JSON"),
                serializer=OaiHarvesterUIJSONSerializer(),
            ),
            **entrypoint_response_handlers,
        }

    @property
    def error_handlers(self):
        entrypoint_error_handlers = {}
        for x in importlib.metadata.entry_points(
            group="invenio.oarepo_oaipmh_harvester.oai_harvester_record.error_handlers"
        ):
            entrypoint_error_handlers.update(x.load())
        return {**super().error_handlers, **entrypoint_error_handlers}

    @property
    def request_body_parsers(self):
        entrypoint_request_bodyparsers = {}
        for x in importlib.metadata.entry_points(
            group="invenio.oarepo_oaipmh_harvester.oai_harvester_record.request_bodyparsers"
        ):
            entrypoint_request_bodyparsers.update(x.load())
        return {
            **super().request_body_parsers,
            **entrypoint_request_bodyparsers,
        }
