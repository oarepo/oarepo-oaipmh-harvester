# SPDX-FileCopyrightText: 2023-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Registry of OAI-PMH harvesters.

A harvester ([OAIHarvester][oarepo_oaipmh_harvester.oai_harvester.models.OAIHarvester]) is
a plain database model wrapped by
[OAIHarvesterAggregate][oarepo_oaipmh_harvester.oai_harvester.api.OAIHarvesterAggregate] so
that the standard records-resources service machinery (search, facets, indexing, links)
can be used.
[OAIHarvesterService][oarepo_oaipmh_harvester.oai_harvester.service.OAIHarvesterService]
adds the `harvest` action which starts the harvest Celery task; creating a harvester also
registers its invenio-jobs job type (see [jobs][oarepo_oaipmh_harvester.jobs]).
"""

from __future__ import annotations
