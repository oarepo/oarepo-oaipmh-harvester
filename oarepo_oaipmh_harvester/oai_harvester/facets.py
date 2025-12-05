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

base_url = TermsFacet(field="base_url", label=_("Base URL"))

name = TermsFacet(field="name", label=_("Name"))

metadata_prefix = TermsFacet(field="metadata_prefix", label=_("Metadata Prefix"))

setspec = TermsFacet(field="setspec", label=_("Set Specifications"))

loader = TermsFacet(field="loader", label=_("Loader"))

transformers = TermsFacet(field="transformers", label=_("Transformers"))

writers = TermsFacet(field="writers", label=_("Writers"))

harvest_managers = TermsFacet(field="harvest_managers.user", label=_("Harvest Managers"))
