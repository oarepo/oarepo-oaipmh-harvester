# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Facets for OAI Harvester."""

from __future__ import annotations

from invenio_i18n import lazy_gettext as _
from invenio_records_resources.services.records.facets.facets import TermsFacet

base_url = TermsFacet(field="base_url", label=_("Base URL"))

name = TermsFacet(field="name", label=_("Name"))

metadata_prefix = TermsFacet(field="metadata_prefix", label=_("Metadata Prefix"))

setspec = TermsFacet(field="setspec", label=_("Set Specifications"))

loader = TermsFacet(field="loader", label=_("Loader"))

transformers = TermsFacet(field="transformers", label=_("Transformers"))

writers = TermsFacet(field="writers", label=_("Writers"))

harvest_managers = TermsFacet(field="harvest_managers.user", label=_("Harvest Managers"))
