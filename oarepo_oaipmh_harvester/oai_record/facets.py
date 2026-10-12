# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Facets for OAI Harvester."""

from __future__ import annotations

from invenio_i18n import lazy_gettext as _
from invenio_records_resources.services.records.facets.facets import TermsFacet

harvester = TermsFacet(field="harvester_id", label=_("Harvester ID"))

deleted = TermsFacet(
    field="deleted",
    label=_("Deleted"),
    value_labels={True: _("Yes"), False: _("No")},
)

has_errors = TermsFacet(
    field="has_errors",
    label=_("Errors"),
    value_labels={True: _("Yes"), False: _("No")},
)
has_warnings = TermsFacet(
    field="has_warnings",
    label=_("Warnings"),
    value_labels={True: _("Yes"), False: _("No")},
)
error_code = TermsFacet(
    field="errors.type",
    label=_("Error type"),
)
error_message = TermsFacet(
    field="errors.message",
    label=_("Error message"),
)
error_location = TermsFacet(
    field="errors.location",
    label=_("Error location"),
)
