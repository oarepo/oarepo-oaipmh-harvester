# SPDX-FileCopyrightText: 2023-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Permission policies and generators for harvesters and harvest records.

* [OAIHarvesterPermissionPolicy][oarepo_oaipmh_harvester.permissions.OAIHarvesterPermissionPolicy]
  - administrators manage harvesters; harvest managers
  ([HarvestManager][oarepo_oaipmh_harvester.permissions.HarvestManager], user ids in the
  harvester's `harvest_managers`) may read a harvester and run it.
* [OAIRecordPermissionPolicy][oarepo_oaipmh_harvester.permissions.OAIRecordPermissionPolicy]
  - harvest records are written by the system only; administrators and the managers of the
  record's harvester ([HarvestRecordManager][oarepo_oaipmh_harvester.permissions.HarvestRecordManager])
  may read them and re-harvest them.

Both manager generators also provide search query filters, so that managers only find
their own harvesters / records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from flask_principal import Need, UserNeed
from invenio_records_permissions import RecordPermissionPolicy
from invenio_records_permissions.generators import (
    AnyUser,
    AuthenticatedUser,
    Generator,
    SystemProcess,
)
from oarepo_runtime.services.generators import AdministrationWithQueryFilter
from opensearch_dsl.query import MatchNone, Term

if TYPE_CHECKING:
    from collections.abc import Collection

    from invenio_search.engine import dsl


class HarvestManager(Generator):
    """Grants harvest managers access to the harvesters they manage."""

    @override
    def needs(self, **kwargs: Any) -> Collection[Need]:
        """Return the needs for harvest managers."""
        if "record" not in kwargs:
            return []
        record = kwargs["record"]
        return [UserNeed(manager["user"]) for manager in record.get("harvest_managers", []) if "user" in manager]

    @override
    def query_filter(self, **kwargs: Any) -> dsl.query.Query | list[dsl.query.Query] | None:
        """Restrict search to harvesters managed by the identity."""
        identity = kwargs["identity"]
        if not identity or not identity.id:
            return MatchNone()
        return Term(**{"harvest_managers.user": identity.id})


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
        """Restrict search to records of harvesters managed by the identity."""
        identity = kwargs["identity"]
        if not identity or not identity.id:
            return MatchNone()
        return Term(**{"harvest_managers.user": identity.id})


class OAIRecordPermissionPolicy(RecordPermissionPolicy):
    """Permission policy for harvested records."""

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
