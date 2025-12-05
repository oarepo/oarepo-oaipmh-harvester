#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Permissions for OAI-PMH Harvester."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from flask_principal import Need, UserNeed
from invenio_access import action_factory
from invenio_access.models import ActionRoles, ActionUsers
from invenio_administration.generators import (
    Administration,
    administration_access_action,
)
from invenio_records_permissions import RecordPermissionPolicy
from invenio_records_permissions.generators import (
    AnyUser,
    AuthenticatedUser,
    Generator,
    SystemProcess,
)
from opensearch_dsl.query import MatchAll, MatchNone, Term

if TYPE_CHECKING:
    from collections.abc import Collection

    from invenio_search.engine import dsl


class HarvestManager(Generator):
    """Enables access to logs for harvest managers."""

    @override
    def needs(self, **kwargs: Any) -> Collection[Need]:
        """Return the needs for harvest managers."""
        if "record" not in kwargs:
            return []
        record = kwargs["record"]
        return [UserNeed(manager["user"]) for manager in record.get("harvest_managers", []) if "user" in manager]

    @override
    def query_filter(self, **kwargs: Any) -> dsl.query.Query | list[dsl.query.Query] | None:
        """Search filters."""
        identity = kwargs["identity"]
        if not identity or not identity.id:
            return MatchNone()
        return Term(**{"harvest_managers.user": identity.id})


class ActionQueryFilterMixin:
    """Administration mixin that filters users based on action access."""

    access_action: Any

    def query_filter(self, **kwargs: Any) -> dsl.query.Query | list[dsl.query.Query] | None:
        """Return search filter that allows all in case user (or one of the roles the user belongs to) has access."""
        identity = kwargs["identity"]
        user_ids = [need.value for need in identity.provides if need.method == "id"]

        if user_ids:
            has_direct_access = ActionUsers.query.filter(
                ActionUsers.user_id == user_ids[0],
                ActionUsers.action == self.access_action.value,
                ActionUsers.exclude.is_(False),
            ).count()
            if has_direct_access:
                return MatchAll()

        user_roles = [need.value for need in identity.provides if need.method == "role"]
        if user_roles:
            has_access_through_roles = ActionRoles.query.filter(
                ActionRoles.role_id.in_(user_roles),
                ActionRoles.action == self.access_action.value,
                ActionRoles.exclude.is_(False),
            ).count()
            if has_access_through_roles:
                return MatchAll()

        # If no direct access or roles, return no match
        return MatchNone()


class AdministrationWithQueryFilter(ActionQueryFilterMixin, Administration):
    """Administration generator which matches people with administration-access permission."""

    access_action = administration_access_action


harvest_action = action_factory("oai-harvest-access")


class HarvestAction(ActionQueryFilterMixin, Generator):
    """Generator that matches people with harvest-access permission."""

    access_action = harvest_action

    @override
    def needs(self, **kwargs: Any) -> Collection[Need]:
        return [harvest_action]  # type: ignore[reportReturnType]


class OAIHarvesterPermissionPolicy(RecordPermissionPolicy):
    """Permission policy for OAI Harvester records."""

    can_search = (SystemProcess(), AnyUser())
    can_read = (SystemProcess(), AdministrationWithQueryFilter(), HarvestManager())
    can_create = (SystemProcess(), AdministrationWithQueryFilter())
    can_update = (SystemProcess(), AdministrationWithQueryFilter())
    can_delete = (SystemProcess(), AdministrationWithQueryFilter())
    can_manage = (SystemProcess(), AdministrationWithQueryFilter())
    can_run_harvest = (
        SystemProcess(),
        AdministrationWithQueryFilter(),
        HarvestManager(),
    )

    can_create_files = (SystemProcess(), AdministrationWithQueryFilter())
    can_set_content_files = (SystemProcess(), AdministrationWithQueryFilter())
    can_get_content_files = (SystemProcess(), AdministrationWithQueryFilter())
    can_commit_files = (SystemProcess(), AdministrationWithQueryFilter())
    can_read_files = (SystemProcess(), AdministrationWithQueryFilter())
    can_update_files = (SystemProcess(), AdministrationWithQueryFilter())
    can_delete_files = (SystemProcess(), AdministrationWithQueryFilter())

    can_edit = (SystemProcess(),)
    can_new_version = (SystemProcess(),)
    can_search_drafts = (SystemProcess(),)
    can_read_draft = (SystemProcess(),)
    can_update_draft = (SystemProcess(),)
    can_delete_draft = (SystemProcess(),)
    can_publish = (SystemProcess(),)
    can_draft_create_files = (SystemProcess(),)
    can_draft_set_content_files = (SystemProcess(),)
    can_draft_get_content_files = (SystemProcess(),)
    can_draft_commit_files = (SystemProcess(),)
    can_draft_read_files = (SystemProcess(),)
    can_draft_update_files = (SystemProcess(),)


class HarvestRecordManager(Generator):
    """Generator for giving access to harvested records for harvest record managers."""

    @override
    def needs(self, **kwargs: Any) -> Collection[Need]:
        """Return the needs for harvest record managers."""
        if "record" not in kwargs:
            return []

        harvester = kwargs["record"].harvester

        return [UserNeed(manager["user"]) for manager in (harvester.harvest_managers or []) if "user" in manager]

    def query_filter(self, **kwargs: Any) -> dsl.query.Query | list[dsl.query.Query] | None:
        """Return search filter for harvest record managers."""
        identity = kwargs["identity"]
        if not identity or not identity.id:
            return MatchNone()
        return Term(**{"harvest_managers.user": identity.id})


class OAIRecordPermissionPolicy(RecordPermissionPolicy):
    """Permission policy for users and user groups."""

    can_create = (SystemProcess(),)
    can_read = (
        SystemProcess(),
        AdministrationWithQueryFilter(),
        HarvestRecordManager(),
    )
    can_run_harvest = (
        SystemProcess(),
        AdministrationWithQueryFilter(),
        HarvestRecordManager(),
    )
    can_search = (AuthenticatedUser(), SystemProcess())
    can_update = (SystemProcess(),)
    can_delete = (SystemProcess(),)
