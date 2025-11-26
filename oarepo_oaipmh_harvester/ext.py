import re
from functools import cached_property
from io import StringIO
from typing import Union

import yaml
from invenio_base.utils import obj_or_import_string

from oarepo_oaipmh_harvester import cli  # noqa
from oarepo_oaipmh_harvester.harvester import harvest
from oarepo_oaipmh_harvester.oai_harvester.records.api import OaiHarvesterRecord

from . import config


class OARepoOAIHarvesterExt(object):
    """extension."""

    def __init__(self, app=None):
        """Extension initialization."""
        if app:
            self.init_app(app)

    def init_app(self, app):
        """Flask application initialization."""
        self.app = app
        app.extensions["oarepo_oaipmh_harvester"] = self
        self.load_config(app)

    def run(
        self,
        harvester_or_code: Union[str, OaiHarvesterRecord],
        all_records=False,
        on_background=False,
        identifiers=None,
    ):
        harvest(
            harvester_or_code=harvester_or_code,
            all_records=all_records,
            on_background=on_background,
            identifiers=identifiers,
        )

    def get_parser_signature(self, parser_name, **kwargs) -> Signature:
        parser_name, args = split_processor_name(parser_name)
        return Signature(
            kind=SignatureKind.READER, name=parser_name, kwargs={**args, **kwargs}
        )

    def get_transformer_signature(self, transformer, **kwargs) -> Signature:
        transformer, args = split_processor_name(transformer)
        return Signature(
            kind=SignatureKind.TRANSFORMER, name=transformer, kwargs={**args, **kwargs}
        )

    def get_writer_signature(self, writer, **kwargs) -> Signature:
        writer, args = split_processor_name(writer)
        return Signature(
            kind=SignatureKind.WRITER, name=writer, kwargs={**args, **kwargs}
        )

    def load_config(self, app):
        app.config.setdefault("DATASTREAMS_READERS", {}).update(
            config.DATASTREAMS_READERS
        )

        app.config.setdefault("DATASTREAMS_TRANSFORMERS", {}).update(
            config.DATASTREAMS_TRANSFORMERS
        )

        app.config.setdefault("DATASTREAMS_WRITERS", {}).update(
            config.DATASTREAMS_WRITERS
        )

        app.config.setdefault("OAREPO_PERMISSIONS_PRESETS", {}).update(
            config.OAREPO_PERMISSIONS_PRESETS
        )

        app.config.setdefault("OAI_RUN_SEARCH", config.OAI_RUN_SEARCH)
        app.config.setdefault("OAI_RUN_FACETS", config.OAI_RUN_FACETS)
        app.config.setdefault("OAI_RUN_SORT_OPTIONS", config.OAI_RUN_SORT_OPTIONS)
        app.config.setdefault(
            "OAI_HARVESTER_SORT_OPTIONS", config.OAI_HARVESTER_SORT_OPTIONS
        )
        app.config.setdefault("OAI_HARVESTER_SEARCH", config.OAI_HARVESTER_SEARCH)
        app.config.setdefault("OAI_HARVESTER_FACETS", config.OAI_HARVESTER_FACETS)
        app.config.setdefault("OAI_RECORD_SEARCH", config.OAI_RECORD_SEARCH)
        app.config.setdefault("OAI_RECORD_SORT_OPTIONS", config.OAI_RECORD_SORT_OPTIONS)
        app.config.setdefault("OAI_RECORD_FACETS", config.OAI_RECORD_FACETS)

        app.config.setdefault(
            "OAI_RUN_REINDEX_THRESHOLD", config.OAI_RUN_REINDEX_THRESHOLD
        )

    @cached_property
    def oai_run_service_config(self):
        """Get the OAI run service config."""
        return obj_or_import_string(
            self.app.config.get(
                "OAI_RUN_SERVICE_CONFIG",
                "oarepo_oaipmh_harvester.oai_run.service:OAIRunServiceConfig",
            ),
        ).build(self.app)

    @cached_property
    def oai_run_service(self):
        """Get the OAI run service."""
        return obj_or_import_string(
            self.app.config.get(
                "OAI_RUN_SERVICE",
                "oarepo_oaipmh_harvester.oai_run.service:OAIRunService",
            ),
        )(self.oai_run_service_config)

    @cached_property
    def oai_run_resource_config(self):
        """Get the OAI run resource config."""
        return obj_or_import_string(
            self.app.config.get(
                "OAI_RUN_RESOURCE_CONFIG",
                "oarepo_oaipmh_harvester.oai_run.resource:OAIRunResourceConfig",
            ),
        )()

    @cached_property
    def oai_run_resource(self):
        """Get the OAI run resource."""
        return obj_or_import_string(
            self.app.config.get(
                "OAI_RUN_RESOURCE",
                "oarepo_oaipmh_harvester.oai_run.resource:OAIRunResource",
            ),
        )(self.oai_run_resource_config, self.oai_run_service)

    @cached_property
    def oai_record_service_config(self):
        """Get the OAI record service config."""
        return obj_or_import_string(
            self.app.config.get(
                "OAI_RECORD_SERVICE_CONFIG",
                "oarepo_oaipmh_harvester.oai_record.service:OAIRecordServiceConfig",
            ),
        ).build(self.app)

    @cached_property
    def oai_record_service(self):
        """Get the OAI record service."""
        return obj_or_import_string(
            self.app.config.get(
                "OAI_RECORD_SERVICE",
                "oarepo_oaipmh_harvester.oai_record.service:OAIRecordService",
            ),
        )(self.oai_record_service_config)

    @cached_property
    def oai_record_resource_config(self):
        """Get the OAI record resource config."""
        return obj_or_import_string(
            self.app.config.get(
                "OAI_RECORD_RESOURCE_CONFIG",
                "oarepo_oaipmh_harvester.oai_record.resource:OAIRecordResourceConfig",
            ),
        )()

    @cached_property
    def oai_record_resource(self):
        """Get the OAI record resource."""
        return obj_or_import_string(
            self.app.config.get(
                "OAI_RECORD_RESOURCE",
                "oarepo_oaipmh_harvester.oai_record.resource:OAIRecordResource",
            ),
        )(self.oai_record_resource_config, self.oai_record_service)


def split_processor_name(processor):
    if "{" not in processor:
        return processor, {}
    processor, rest = processor.split("{", maxsplit=1)
    rest = "{" + rest
    rest = re.sub(r"([^\\])=", r"\1: ", rest)
    rest = re.sub(r"\\(.)", r"\1", rest)
    args = yaml.safe_load(StringIO(rest))
    return processor, args


def finalize_app(app):
    init(app)


def api_finalize_app(app):
    init(app)


def init(app):
    """Init app."""
    sregistry = app.extensions["invenio-records-resources"].registry
    ext = app.extensions["oarepo_oaipmh_harvester"]
    sregistry.register(
        ext.oai_run_service, service_id=ext.oai_run_service_config.service_id
    )
    sregistry.register(
        ext.oai_record_service, service_id=ext.oai_record_service_config.service_id
    )
    # Register indexers
    iregistry = app.extensions["invenio-indexer"].registry
    iregistry.register(
        ext.oai_run_service.indexer,
        indexer_id=ext.oai_run_service_config.service_id,
    )
    iregistry.register(
        ext.oai_record_service.indexer,
        indexer_id=ext.oai_record_service_config.service_id,
    )
