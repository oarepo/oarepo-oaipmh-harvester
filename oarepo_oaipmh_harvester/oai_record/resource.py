#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""OAI Record resource config."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, override

import marshmallow as ma
import yaml
from flask import Response, g
from flask_resources import resource_requestctx, response_handler, route
from flask_resources.responses import ResponseHandler
from flask_resources.serializers.json import JSONSerializer
from invenio_records_resources.resources import (
    RecordResource,
    RecordResourceConfig,
)
from invenio_records_resources.resources.errors import ErrorHandlersMixin
from invenio_records_resources.resources.records.headers import etag_headers
from invenio_records_resources.resources.records.resource import (
    request_search_args,
    request_view_args,
)
from invenio_records_resources.resources.records.utils import search_preference
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import YamlLexer

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from werkzeug.exceptions import HTTPException


def data_to_html_yaml(data: Any) -> str:
    """Convert data to HTML highlighted YAML."""
    yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return highlight(yaml_str, YamlLexer(), HtmlFormatter(full=False))  # type: ignore[no-any-return]


class AdministrationDetailJSONSerializer(JSONSerializer):
    """JSON serializer for administration API."""

    @override
    def serialize_object(self, obj: Any) -> str:
        """Serialize a single object."""
        obj = self._convert_to_administration_detail(obj)
        return super().serialize_object(obj)  # type: ignore[no-any-return]

    @override
    def serialize_object_list(self, obj_list: dict[str, Any]) -> str:
        obj_list["hits"]["hits"] = [self._convert_to_administration_detail(obj) for obj in obj_list["hits"]["hits"]]
        return super().serialize_object_list(obj_list)  # type: ignore[no-any-return]

    def _convert_to_administration_detail(self, serialized_record: dict[str, Any]) -> dict[str, Any]:
        serialized_record = {**serialized_record}
        tr = serialized_record.get("transformed_data", {})
        if tr:
            serialized_record["title"] = tr.get("metadata", {}).get("title", "") or tr.get("title", "")
            if serialized_record["title"]:
                serialized_record["title"] = str(serialized_record["title"])
            record_link = tr.get("links", {}).get("self_html")
            if record_link:
                serialized_record["record_id_with_link"] = '<a href="{}">{}</a>'.format(
                    record_link, serialized_record["id"]
                )
            else:
                serialized_record["record_id_with_link"] = serialized_record["id"]
        serialized_record["errors"] = data_to_html_yaml(serialized_record.get("errors"))
        serialized_record["original_data"] = data_to_html_yaml(serialized_record.get("original_data"))
        serialized_record["transformed_data"] = data_to_html_yaml(serialized_record.get("transformed_data"))
        serialized_record["has_errors"] = "Yes" if serialized_record.get("has_errors") else "No"
        serialized_record["deleted"] = "Yes" if serialized_record.get("deleted") else "No"
        return serialized_record


#
# Resource config
#
class OAIRecordResourceConfig(RecordResourceConfig):
    """OAI Runs resource configuration."""

    blueprint_name = "oai_records"
    url_prefix = "/oai/harvest/records"
    api_service = "oai-harvest-record"

    routes: Mapping[str, Any] = {
        "list": "",
        "item": "/<path:id>",
        "harvest": "/<path:id>/harvest",
    }

    request_view_args: Mapping[str, Any] = {
        "id": ma.fields.Str(),
    }

    error_handlers: ClassVar[  # type: ignore[misc] # overriding with class var
        dict[
            type[HTTPException | BaseException] | int,
            Callable[[Exception], Response],
        ]
    ] = {
        **ErrorHandlersMixin.error_handlers,
    }

    response_handlers: Mapping[str, Any] = {
        "application/vnd.inveniordm.v1+json": RecordResourceConfig.response_handlers["application/json"],
        "application/invenio-administration-detail+json": ResponseHandler(
            serializer=AdministrationDetailJSONSerializer(),
            headers=etag_headers,
        ),
        **RecordResourceConfig.response_handlers,
    }


class OAIRecordResource(RecordResource):
    """OAI Record resource."""

    def p(self, prefix: str, route: str) -> str:
        """Prefix a route with the URL prefix."""
        return f"{prefix}{route}"

    def create_url_rules(self) -> list:
        """Create the URL rules for the users resource."""
        routes = self.config.routes
        return [
            route("GET", routes["list"], self.search),
            route("GET", routes["item"], self.read),
            route("POST", routes["harvest"], self.harvest),
        ]

    @override
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

    @override
    @request_view_args
    @response_handler()
    def read(self) -> tuple[dict[str, Any], int]:
        """Read a user."""
        item = self.service.read(
            id_=resource_requestctx.view_args["id"],
            identity=g.identity,
        )
        return item.to_dict(), 200

    @request_view_args
    @response_handler()
    def harvest(self) -> tuple[dict[str, Any], int]:
        """Re-harvest the OAI record."""
        item = self.service.harvest(
            id_=resource_requestctx.view_args["id"],
            identity=g.identity,
        )
        return item.to_dict(), 200
