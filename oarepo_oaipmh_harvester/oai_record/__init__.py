# SPDX-FileCopyrightText: 2023-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Harvest records - tracking of harvested OAI-PMH records.

[OAIHarvestedRecord][oarepo_oaipmh_harvester.oai_record.models.OAIHarvestedRecord] keeps
one row per harvested OAI identifier: the OAI datestamp and deleted flag, the original XML
payload, the transformed data, the pid and type of the local record it was written to and
the errors of the last write. It is written by the `oai-service` writer
([oai_service][oarepo_oaipmh_harvester.writers.oai_service]) and its datestamp / deleted
flag / error state decide whether the next harvest can skip the record.

The service exposes search with facets over harvester, deleted flag and error code /
message / location; the dumper adds the harvester (and its managers, used by permission
query filters) to the search documents. The `harvest` action re-harvests a single record.
"""

from __future__ import annotations
