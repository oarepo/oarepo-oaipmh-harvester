#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""OAI-PMH Harvester extension."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, cast

from invenio_base.utils import obj_or_import_string

from oarepo_oaipmh_harvester.oai_harvester.resource import (
    OAIHarvesterResource,
    OAIHarvesterResourceConfig,
)
from oarepo_oaipmh_harvester.oai_harvester.service import (
    OAIHarvesterService,
    OAIHarvesterServiceConfig,
)
from oarepo_oaipmh_harvester.oai_record.resource import (
    OAIRecordResource,
    OAIRecordResourceConfig,
)
from oarepo_oaipmh_harvester.oai_record.service import (
    OAIRecordService,
    OAIRecordServiceConfig,
)

if TYPE_CHECKING:
    from flask import Flask


class OARepoOAIHarvesterExt:
    """OAI-PMH Harvester extension."""

    def __init__(self, app: Flask | None = None):
        """Extension initialization."""
        if app:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """Flask application initialization."""
        self.app = app
        app.extensions["oarepo_oaipmh_harvester"] = self
        self.init_config(app)

    def init_config(self, app: Flask) -> None:
        """Initialize configuration."""
        from invenio_vocabularies import config as vocabularies_config

        from . import config as harvester_config

        if "VOCABULARIES_DATASTREAM_TRANSFORMERS" not in app.config:
            app.config["VOCABULARIES_DATASTREAM_TRANSFORMERS"] = {
                **vocabularies_config.VOCABULARIES_DATASTREAM_TRANSFORMERS
            }
        app.config["VOCABULARIES_DATASTREAM_TRANSFORMERS"].update(harvester_config.VOCABULARIES_DATASTREAM_TRANSFORMERS)
        if "VOCABULARIES_DATASTREAM_WRITERS" not in app.config:
            app.config["VOCABULARIES_DATASTREAM_WRITERS"] = {**vocabularies_config.VOCABULARIES_DATASTREAM_WRITERS}
        app.config["VOCABULARIES_DATASTREAM_WRITERS"].update(harvester_config.VOCABULARIES_DATASTREAM_WRITERS)

        app.config.setdefault(
            "OAI_HARVESTER_DEFAULT_BATCH_SIZE",
            harvester_config.OAI_HARVESTER_DEFAULT_BATCH_SIZE,
        )

        app.config.setdefault(
            "OAI_HARVESTER_SORT_OPTIONS",
            harvester_config.OAI_HARVESTER_SORT_OPTIONS,
        )
        app.config.setdefault(
            "OAI_HARVESTER_SEARCH",
            harvester_config.OAI_HARVESTER_SEARCH,
        )
        app.config.setdefault(
            "OAI_HARVESTER_FACETS",
            harvester_config.OAI_HARVESTER_FACETS,
        )
        app.config.setdefault(
            "OAI_RECORD_SORT_OPTIONS",
            harvester_config.OAI_RECORD_SORT_OPTIONS,
        )
        app.config.setdefault(
            "OAI_RECORD_SEARCH",
            harvester_config.OAI_RECORD_SEARCH,
        )
        app.config.setdefault(
            "OAI_RECORD_FACETS",
            harvester_config.OAI_RECORD_FACETS,
        )

    @cached_property
    def oai_record_service_config(self) -> OAIRecordServiceConfig:
        """Get the OAI record service config."""
        config_cls = obj_or_import_string(  # type: ignore[no-any-return]
            self.app.config.get(
                "OAI_RECORD_SERVICE_CONFIG",
                "oarepo_oaipmh_harvester.oai_record.service:OAIRecordServiceConfig",
            ),
        )
        if config_cls is None:
            raise RuntimeError("OAI_RECORD_SERVICE_CONFIG is not configured")
        if not issubclass(config_cls, OAIRecordServiceConfig):
            raise TypeError("OAI_RECORD_SERVICE_CONFIG is not a subclass of OAIRecordServiceConfig")
        return cast("OAIRecordServiceConfig", config_cls.build(self.app))

    @cached_property
    def oai_record_service(self) -> OAIRecordService:
        """Get the OAI record service."""
        return obj_or_import_string(  # type: ignore[no-any-return]
            self.app.config.get(
                "OAI_RECORD_SERVICE",
                "oarepo_oaipmh_harvester.oai_record.service:OAIRecordService",
            ),
        )(self.oai_record_service_config)

    @cached_property
    def oai_record_resource_config(self) -> OAIRecordResourceConfig:
        """Get the OAI record resource config."""
        return obj_or_import_string(  # type: ignore[no-any-return]
            self.app.config.get(
                "OAI_RECORD_RESOURCE_CONFIG",
                "oarepo_oaipmh_harvester.oai_record.resource:OAIRecordResourceConfig",
            ),
        )()

    @cached_property
    def oai_record_resource(self) -> OAIRecordResource:
        """Get the OAI record resource."""
        resource_cls = obj_or_import_string(  # type: ignore[no-any-return]
            self.app.config.get(
                "OAI_RECORD_RESOURCE",
                "oarepo_oaipmh_harvester.oai_record.resource:OAIRecordResource",
            ),
        )
        if resource_cls is None:
            raise RuntimeError("OAI_RECORD_RESOURCE is not configured")
        if not issubclass(resource_cls, OAIRecordResource):
            raise TypeError("OAI_RECORD_RESOURCE is not a subclass of OAIRecordResource")
        return cast(
            "OAIRecordResource",
            resource_cls(self.oai_record_resource_config, self.oai_record_service),
        )

    @cached_property
    def oai_harvester_service_config(self) -> OAIHarvesterServiceConfig:
        """Get the OAI harvester service config."""
        config_cls = obj_or_import_string(  # type: ignore[no-any-return]
            self.app.config.get(
                "OAI_HARVESTER_SERVICE_CONFIG",
                "oarepo_oaipmh_harvester.oai_harvester.service:OAIHarvesterServiceConfig",
            ),
        )
        if config_cls is None:
            raise RuntimeError("OAI_HARVESTER_SERVICE_CONFIG is not configured")
        if not issubclass(config_cls, OAIHarvesterServiceConfig):
            raise TypeError("OAI_HARVESTER_SERVICE_CONFIG is not a subclass of OAIHarvesterServiceConfig")
        return cast("OAIHarvesterServiceConfig", config_cls.build(self.app))

    @cached_property
    def oai_harvester_service(self) -> OAIHarvesterService:
        """Get the OAI harvester service."""
        service_cls = obj_or_import_string(  # type: ignore[no-any-return]
            self.app.config.get(
                "OAI_HARVESTER_SERVICE",
                "oarepo_oaipmh_harvester.oai_harvester.service:OAIHarvesterService",
            ),
        )
        if service_cls is None:
            raise RuntimeError("OAI_HARVESTER_SERVICE is not configured")
        if not issubclass(service_cls, OAIHarvesterService):
            raise TypeError("OAI_HARVESTER_SERVICE is not a subclass of OAIHarvesterService")
        return cast("OAIHarvesterService", service_cls(self.oai_harvester_service_config))

    @cached_property
    def oai_harvester_resource_config(self) -> OAIHarvesterResourceConfig:
        """Get the OAI harvester resource config."""
        config_cls = obj_or_import_string(  # type: ignore[no-any-return]
            self.app.config.get(
                "OAI_HARVESTER_RESOURCE_CONFIG",
                "oarepo_oaipmh_harvester.oai_harvester.resource:OAIHarvesterResourceConfig",
            ),
        )
        if config_cls is None:
            raise RuntimeError("OAI_HARVESTER_RESOURCE_CONFIG is not configured")
        if not issubclass(config_cls, OAIHarvesterResourceConfig):
            raise TypeError("OAI_HARVESTER_RESOURCE_CONFIG is not a subclass of OAIHarvesterResourceConfig")
        return cast("OAIHarvesterResourceConfig", config_cls())

    @cached_property
    def oai_harvester_resource(self) -> OAIHarvesterResource:
        """Get the OAI harvester resource."""
        resource_cls = obj_or_import_string(  # type: ignore[no-any-return]
            self.app.config.get(
                "OAI_HARVESTER_RESOURCE",
                "oarepo_oaipmh_harvester.oai_harvester.resource:OAIHarvesterResource",
            ),
        )
        if resource_cls is None:
            raise RuntimeError("OAI_HARVESTER_RESOURCE is not configured")
        if not issubclass(resource_cls, OAIHarvesterResource):
            raise TypeError("OAI_HARVESTER_RESOURCE is not a subclass of OAIHarvesterResource")
        return cast(
            "OAIHarvesterResource",
            resource_cls(self.oai_harvester_resource_config, self.oai_harvester_service),
        )


def finalize_apps(app: Flask) -> None:
    """Flask application finalization."""
    from .jobs import register_current_harvesters

    ext: OARepoOAIHarvesterExt = app.extensions["oarepo_oaipmh_harvester"]
    sregistry = app.extensions["invenio-records-resources"].registry
    sregistry.register(
        ext.oai_record_service,
        service_id=ext.oai_record_service_config.service_id,
    )
    sregistry.register(
        ext.oai_harvester_service,
        service_id=ext.oai_harvester_service_config.service_id,
    )

    iregistry = app.extensions["invenio-indexer"].registry
    iregistry.register(
        ext.oai_record_service.indexer,
        indexer_id=ext.oai_record_service_config.service_id,
    )
    iregistry.register(
        ext.oai_harvester_service.indexer,
        indexer_id=ext.oai_harvester_service_config.service_id,
    )
    register_current_harvesters()
