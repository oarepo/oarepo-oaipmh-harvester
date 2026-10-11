#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Registry of OAI-PMH harvesters.

A harvester (:class:`~oarepo_oaipmh_harvester.oai_harvester.models.OAIHarvester`) is a
plain database model wrapped by
:class:`~oarepo_oaipmh_harvester.oai_harvester.api.OAIHarvesterAggregate` so that the
standard records-resources service machinery (search, facets, indexing, links) can be
used. :class:`~oarepo_oaipmh_harvester.oai_harvester.service.OAIHarvesterService` adds
the ``harvest`` action which starts the harvest Celery task; creating a harvester also
registers its invenio-jobs job type (see :mod:`oarepo_oaipmh_harvester.jobs`).
"""

from __future__ import annotations
