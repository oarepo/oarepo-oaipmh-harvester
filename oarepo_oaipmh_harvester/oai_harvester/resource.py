#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""OAI Harvester HTTP resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

import yaml
from flask import g
from flask_resources import (
    ResponseHandler,
    resource_requestctx,
    response_handler,
    route,
)
from flask_resources.serializers.json import JSONSerializer
from invenio_records_resources.resources import RecordResource, RecordResourceConfig
from invenio_records_resources.resources.records.headers import etag_headers
from invenio_records_resources.resources.records.resource import (
    request_search_args,
    request_view_args,
)
from invenio_records_resources.resources.records.utils import search_preference
from invenio_records_resources.services.base.config import ConfiguratorMixin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import YamlLexer

if TYPE_CHECKING:
    from collections.abc import Mapping


def data_to_html_yaml(data: Any) -> str:
    """Convert data to HTML-formatted YAML string."""
    yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)
    return highlight(yaml_str, YamlLexer(), HtmlFormatter(full=False))  # type: ignore[no-any-return]


class AdministrationDetailJSONSerializer(JSONSerializer):
    """JSON serializer for administration API."""

    @override
    def serialize_object(self, obj: Any) -> str:
        obj = self._convert_to_administration_detail(obj)
        return super().serialize_object(obj)  # type: ignore[no-any-return]

    @override
    def serialize_object_list(self, obj_list: list[Any]) -> str:
        obj_list = [self._convert_to_administration_detail(obj) for obj in obj_list]
        return super().serialize_object_list(obj_list)  # type: ignore[no-any-return]

    def _convert_to_administration_detail(self, serialized_harvester: dict[str, Any]) -> dict[str, Any]:
        serialized_harvester = {**serialized_harvester}
        serialized_harvester["transformers"] = data_to_html_yaml(serialized_harvester["transformers"])
        serialized_harvester["writers"] = data_to_html_yaml(serialized_harvester["writers"])
        # TODO: link to jobs here
        return serialized_harvester


class OAIHarvesterResourceConfig(RecordResourceConfig, ConfiguratorMixin):
    """OAIHarvesterRecord resource config."""

    blueprint_name = "oarepo-oaipmh-harvester"
    url_prefix = "/oai/harvest/harvesters/"

    api_service = "oarepo-oaipmh-harvesters"
    routes: Mapping[str, str] = {
        "list": "",
        "item": "/<pid_value>",
        "harvest": "/<pid_value>/start",
    }

    @property
    def response_handlers(self) -> Mapping[str, ResponseHandler]:  # type: ignore[override]
        """Get the response handlers for this resource."""
        return {
            "application/json": ResponseHandler(
                serializer=JSONSerializer(),
                headers=etag_headers,
            ),
            "application/vnd.inveniordm.v1+json": ResponseHandler(
                serializer=AdministrationDetailJSONSerializer(),
                headers=etag_headers,
            ),
        }


class OAIHarvesterResource(RecordResource):
    """OAIHarvesterRecord resource."""

    def p(self, prefix: str, route: str) -> str:
        """Prefix a route with the URL prefix."""
        return f"{prefix}{route}"

    def create_url_rules(self) -> list[dict[str, Any]]:
        """Create the URL rules for the users resource."""
        routes = self.config.routes
        return [
            route("GET", routes["list"], self.search),
            route("GET", routes["item"], self.read),
            route("PUT", routes["item"], self.update),
            route("DELETE", routes["item"], self.delete),
            route("POST", routes["harvest"], self.harvest),
        ]

    @request_search_args
    @request_view_args
    @response_handler(many=True)
    def search(self) -> tuple[dict[str, Any], int]:
        """Perform a search over users."""
        hits = self.service.search(
            identity=g.identity,
            params=resource_requestctx.args,
            search_preference=search_preference(),
        )
        return hits.to_dict(), 200

    @request_view_args
    @response_handler()
    def read(self) -> tuple[dict[str, Any], int]:
        """Read an oai harvester."""
        item = self.service.read(
            id_=resource_requestctx.view_args["pid_value"],
            identity=g.identity,
        )
        return item.to_dict(), 200

    @request_view_args
    @response_handler()
    def harvest(self) -> tuple[dict[str, Any], int]:
        """Re-harvest the source."""
        item = self.service.harvest(
            id_=resource_requestctx.view_args["pid_value"],
            identity=g.identity,
        )
        return item.to_dict(), 200
