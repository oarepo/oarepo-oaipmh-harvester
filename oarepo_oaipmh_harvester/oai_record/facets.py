#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
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
    field="errors.code",
    label=_("Error code"),
)
error_message = TermsFacet(
    field="errors.message",
    label=_("Error message"),
)
error_location = TermsFacet(
    field="errors.location",
    label=_("Error location"),
)
