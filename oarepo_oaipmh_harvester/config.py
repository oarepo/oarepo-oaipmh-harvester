#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Configuration for OAI-PMH Harvester."""

from __future__ import annotations

from oarepo_oaipmh_harvester.transformers import OAIImportTransformer
from oarepo_oaipmh_harvester.writers import OAIServiceWriter

VOCABULARIES_DATASTREAM_TRANSFORMERS = {
    "oai-import": OAIImportTransformer,
}

VOCABULARIES_DATASTREAM_WRITERS = {
    "oai-service": OAIServiceWriter,
}

OAI_HARVESTER_DEFAULT_BATCH_SIZE = 100
