#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Views for administration of harvested OAI Records."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, cast

from flask_principal import UserNeed
from invenio_access.permissions import Permission
from invenio_administration.permissions import (
    administration_access_action,
)
from invenio_administration.views.base import (
    AdminResourceDetailView,
    AdminResourceListView,
)
from invenio_i18n import lazy_gettext as _

from ...oai_harvester.models import OAIHarvester

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


def oai_record_permissions_decorator[**P, R_co](
    view: Callable[P, R_co],
) -> Callable[P, R_co]:
    """Decorate view to check permissions for OAI record views."""

    @functools.wraps(view)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R_co:
        """Check permissions for OAI record views."""
        # get all harvesters and their managers
        manager_needs = set()
        for md in OAIHarvester.query.all():
            for manager in md.harvest_managers or []:
                if "user" in manager:
                    manager_needs.add(UserNeed(manager["user"]))
        oai_record_permission = Permission(administration_access_action, *manager_needs)  # type: ignore[reportArgumentType]

        return cast(
            "R_co",
            oai_record_permission.require(http_exception=403)(view)(*args, **kwargs),
        )

    return wrapper


class OAIHarvesterPermissionsMixin:
    """Mixin to add OAI harvester permissions to views."""

    decorators = (oai_record_permissions_decorator,)


class RecordListView(OAIHarvesterPermissionsMixin, AdminResourceListView):
    """Configuration for OAI-PMH sets list view."""

    api_endpoint = "/oai/harvest/records"
    extension_name = "oarepo_oaipmh_harvester"
    name = "oarepo_oaipmh_harvest_records"
    url = "/oarepo/harvest/records"

    resource_config = "oai_record_resource"
    search_request_headers: Mapping[str, str] = {"Accept": "application/invenio-administration-detail+json"}
    title = "OAI-PMH Harvester Records"
    category = "Site management"
    pid_path = "id"
    icon = "exchange"
    order = 1
    menu_label = "OAI-PMH Harvester Records"

    actions: Mapping[str, dict[str, Any]] = {
        # invenio OAI harvester does not support re-harvesting individual items
        # "harvest": {                # noqa: ERA001
        #     "text": "Re-harvest",   # noqa: ERA001
        #     "order": 1,        # noqa: ERA001
        #     "payload_schema": None,   # noqa: ERA001
    }

    display_search = True
    display_delete = False
    display_edit = False
    display_create = False

    item_field_list: Mapping[str, dict[str, Any]] = {
        "oai_identifier": {"text": _("OAI Identifier"), "order": 1, "width": 2},
        "record_id": {
            "text": _("Record ID"),
            "order": 2,
            "width": 2,
            "escape": True,
        },
        "title": {"text": _("Record Title"), "order": 3, "width": 6},
        "datestamp": {"text": _("Datestamp"), "order": 4},
        "harvested_at": {"text": _("Harvested at"), "order": 5},
        "deleted": {"text": _("Deleted"), "order": 6, "width": 1},
        "has_errors": {"text": _("Has errors"), "order": 7, "width": 1},
        "manual": {"text": _("Manual"), "order": 8, "width": 1},
    }

    search_config_name = "OAI_RECORD_SEARCH"
    search_facets_config_name = "OAI_RECORD_FACETS"
    search_sort_config_name = "OAI_RECORD_SORT_OPTIONS"


class RecordDetailView(OAIHarvesterPermissionsMixin, AdminResourceDetailView):
    """Configuration for OAI-PMH sets detail view."""

    url = "/oarepo/harvest/records/<path:pid_value>"
    api_endpoint = "/oai/harvest/records/"
    request_headers: Mapping[str, str] = {"Accept": "application/invenio-administration-detail+json"}
    name = "oarepo_oaipmh_records_detail"
    resource_config = "oai_record_resource_config"
    title = "OAI-PMH Harvester Record"
    extension_name = "oarepo_oaipmh_harvester"

    display_delete = False
    display_edit = False

    list_view_name = "oarepo_oaipmh_harvest_records"
    pid_path = "id"

    actions: Mapping[str, dict[str, Any]] = {
        # invenio OAI harvester does not support re-harvesting individual items
        # "harvest": {                  # noqa: ERA001
        #     "text": "Re-harvest",     # noqa: ERA001
        #     "order": 1,               # noqa: ERA001
        #     "payload_schema": None,   # noqa: ERA001
    }

    item_field_list: Mapping[str, dict[str, Any]] = {
        "title": {"text": _("Record Title"), "order": -1},
        "oai_identifier": {"text": _("OAI Identifier"), "order": 1, "width": 3},
        "record_id_with_link": {
            "text": _("Record ID"),
            "order": 2,
            "width": 3,
            "escape": True,
        },
        "datestamp": {"text": _("Datestamp"), "order": 3},
        "harvested_at": {"text": _("Harvested at"), "order": 3, "width": 1},
        "deleted": {"text": _("Deleted"), "order": 5},
        "has_errors": {"text": _("Has errors"), "order": 6},
        "errors": {"text": _("Errors"), "order": 7, "escape": True},
        "original_data": {"text": _("Original data"), "order": 8, "escape": True},
        "transformed_data": {"text": _("Transformed data"), "order": 9, "escape": True},
    }
