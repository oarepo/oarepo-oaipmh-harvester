#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Harvest records - tracking of harvested OAI-PMH records.

:class:`~oarepo_oaipmh_harvester.oai_record.models.OAIHarvestedRecord` keeps one row per
harvested OAI identifier: the OAI datestamp and deleted flag, the original XML payload,
the transformed data, the pid and type of the local record it was written to and the
errors of the last write. It is written by the ``oai-service`` writer
(:mod:`oarepo_oaipmh_harvester.writers.oai_service`) and its datestamp / deleted flag /
error state decide whether the next harvest can skip the record.

The service exposes search with facets over harvester, deleted flag and error code /
message / location; the dumper adds the harvester (and its managers, used by permission
query filters) to the search documents. The ``harvest`` action re-harvests a single
record.
"""

from __future__ import annotations
