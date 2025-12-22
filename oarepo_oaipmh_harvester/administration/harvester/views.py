#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Views for OAI-PMH Harvester administration."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

from flask_principal import UserNeed
from invenio_access.permissions import Permission
from invenio_administration.permissions import (
    administration_access_action,
)
from invenio_administration.views.base import (
    AdminFormView,
    AdminResourceDetailView,
    AdminResourceListView,
)
from invenio_i18n import lazy_gettext as _

from ...oai_harvester.models import OAIHarvester

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    import marshmallow as ma

P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=True)


def oai_harvester_permissions_decorator[**P, R_co](
    view: Callable[P, R_co],
) -> Callable[P, R_co]:
    """Decorate view to check permissions for OAI harvester views."""

    @functools.wraps(view)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R_co:
        """Check permissions for OAI harvester views."""
        # get all harvesters and their managers
        manager_needs = set()
        for md in OAIHarvester.query.all():
            for manager in md.harvest_managers or []:
                if "user" in manager:
                    manager_needs.add(UserNeed(manager["user"]))
        oai_harvester_permission = Permission(administration_access_action, *manager_needs)  # type: ignore[reportArgumentType]

        return cast(
            "R_co",
            oai_harvester_permission.require(http_exception=403)(view)(*args, **kwargs),
        )

    return wrapper


class OAIHarvesterPermissionsMixin:
    """Mixin to add OAI harvester permissions to views."""

    decorators = (oai_harvester_permissions_decorator,)


class OAIPMHListView(OAIHarvesterPermissionsMixin, AdminResourceListView):
    """Configuration for OAI-PMH sets list view."""

    api_endpoint = "/oai/harvest/harvesters/"
    extension_name = "oarepo_oaipmh_harvester"
    name = "oarepo_oaipmh_harvesters"
    url = "/oarepo/harvesters"

    resource_config = "oai_harvester_resource"
    search_request_headers: Mapping[str, str] = {"Accept": "application/json"}
    title = "OAI-PMH Harvesters"
    category = "Site management"
    pid_path = "id"
    icon = "exchange"
    order = 1
    menu_label = "OAI-PMH Harvesters"

    actions: Mapping[str, dict[str, Any]] = {
        "harvest": {
            "text": "Run",
            "order": 1,
            "payload_schema": None,
        }
    }

    display_search = True
    display_delete = True
    display_create = True
    display_edit = True

    item_field_list: Mapping[str, dict[str, Any]] = {
        "name": {"text": _("Name"), "order": 1},
        "id": {"text": _("Code"), "order": 2},
        "baseurl": {"text": _("Base URL"), "order": 3},
        "metadata_prefix": {"text": _("Metadata prefix"), "order": 4},
    }

    search_config_name = "OAI_HARVESTER_SEARCH"
    search_facets_config_name = "OAI_HARVESTER_FACETS"
    search_sort_config_name = "OAI_HARVESTER_SORT_OPTIONS"

    create_view_name = "oarepo_oaipmh_create"


class OAIPMHDetailView(OAIHarvesterPermissionsMixin, AdminResourceDetailView):
    """Configuration for OAI-PMH sets detail view."""

    url = "/oarepo/harvesters/<pid_value>"
    api_endpoint = "/oai/harvest/harvesters/"
    request_headers: Mapping[str, str] = {"Accept": "application/vnd.inveniordm.v1+json"}
    name = "oarepo_oaipmh_harvesters_detail"
    resource_config = "oai_harvester_resource"
    title = "OAI-PMH Harvesters"
    extension_name = "oarepo_oaipmh_harvester"

    display_delete = True
    display_edit = True

    actions: Mapping[str, dict[str, Any]] = {
        "harvest": {
            "text": "Run",
            "order": 1,
            "payload_schema": None,
        }
    }

    list_view_name = "oarepo_oaipmh_harvesters"
    pid_path = "id"

    item_field_list: Mapping[str, dict[str, Any]] = {
        "name": {"text": _("Name"), "order": 1},
        "id": {"text": _("Code"), "order": 2},
        "setspec": {"text": _("Set specification"), "order": 4},
        "metadata_prefix": {"text": _("Metadata prefix"), "order": 5},
        "baseurl": {"text": _("Base URL"), "order": 6},
        "loader": {"text": _("Loader"), "order": 7},
        "writers": {"text": _("Writer"), "order": 8, "escape": True},
        "batch_size": {"text": _("Batch size"), "order": 9},
        "max_records": {"text": _("Maximum number of records"), "order": 10},
        "transformers": {
            "text": _("Transformers"),
            "escape": True,
            "order": 11,
        },
        "created": {"text": _("Created"), "order": 12},
        "updated": {"text": _("Updated"), "order": 13},
        "comment": {"text": _("Comment"), "order": 14},
        "harvest_managers": {
            "text": _("Harvest managers"),
            "order": 15,
            "escape": True,
        },
    }


class OAIHarvesterFormMixin:
    """Mixin to add OAI harvester form configuration to views."""

    request_headers: Mapping[str, str] = {"Accept": "application/json"}

    form_fields: Mapping[str, dict[str, Any]] = {
        "name": {
            "order": 1,
            "text": _("Name"),
            "required": True,
        },
        "id": {
            "order": 2,
            "text": _("Code"),
            "required": True,
        },
        "baseurl": {
            "order": 3,
            "text": _("Base URL"),
            "required": True,
        },
        "metadata_prefix": {
            "order": 4,
            "text": _("Metadata prefix"),
            "required": True,
        },
        "setspec": {
            "order": 6,
            "text": _("Set specification"),
            "required": False,
        },
        "loader": {
            "order": 9,
            "text": _("loader"),
        },
        "transformers": {
            "order": 10,
            "text": _("transformers"),
            "description": _(
                "A list of transformers, separated by newlines. "
                "Parameters might be passed as json after the transformer name. "
                'For example xslt{"url": "https://example.com/xslt.xsl"}'
            ),
            "type": "textarea",
            "rows": 4,
        },
        "writers": {
            "order": 9,
            "text": _("Writers"),
            "description": _("A list of writers, separated by newlines."),
            "type": "textarea",
            "rows": 2,
        },
        "harvest_managers": {
            "order": 12,
            "text": _("Harvest managers"),
            "description": _("Email addresses of harvest managers separated by newlines."),
            "type": "textarea",
            "rows": 4,
        },
    }

    def _schema_to_json(self, schema: ma.Schema) -> dict[str, Any]:
        """Convert schema to JSON representation."""
        ret: dict[str, Any] = super()._schema_to_json(schema)  # type: ignore[misc]
        # TODO: RDM13 has better support for admin fields, will need to be changed then
        ret.pop("harvest_managers", None)
        ret.pop("writers", None)
        ret["transformers"] = {
            "type": "string",
        }
        ret["writers"] = {"type": "string"}
        ret["harvest_managers"] = {"type": "string"}
        ret["setspec"] = {"type": "string"}
        return ret


class OAIPMHEditView(OAIHarvesterPermissionsMixin, OAIHarvesterFormMixin, AdminFormView):  # OarepoAdminFormView):
    """Configuration for OAI-PMH sets edit view."""

    name = "oarepo_oaipmh_edit"
    url = "/oarepo/harvesters/<pid_value>/edit"
    resource_config = "oai_harvester_resource"
    pid_path = "id"
    api_endpoint = "/oai/harvest/harvesters/"
    title = "Edit OAI-PMH harvester"
    extension_name = "oarepo_oaipmh_harvester"
    template = "invenio_administration/edit.html"
    list_view_name = "oarepo_oaipmh_harvesters"


class OAIPMHCreateView(OAIHarvesterPermissionsMixin, OAIHarvesterFormMixin, AdminFormView):
    """Configuration for OAI-PMH sets create view."""

    name = "oarepo_oaipmh_create"
    url = "/oarepo/harvesters/create"
    resource_config = "oai_harvester_resource"
    pid_path = "id"
    api_endpoint = "/oai/harvest/harvesters/"
    title = "Create OAI-PMH Harvester"
    extension_name = "oarepo_oaipmh_harvester"
    list_view_name = "oarepo_oaipmh_harvesters"
    template = "invenio_administration/create.html"
