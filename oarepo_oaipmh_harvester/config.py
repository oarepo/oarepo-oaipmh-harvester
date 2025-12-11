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

from typing import Any

from invenio_i18n import lazy_gettext as _

from oarepo_oaipmh_harvester.oai_harvester import facets
from oarepo_oaipmh_harvester.oai_record import facets as record_facets
from oarepo_oaipmh_harvester.transformers import OAIImportTransformer
from oarepo_oaipmh_harvester.writers import OAIServiceWriter

VOCABULARIES_DATASTREAM_TRANSFORMERS = {
    "oai-import": OAIImportTransformer,
}

VOCABULARIES_DATASTREAM_WRITERS = {
    "oai-service": OAIServiceWriter,
}

OAI_HARVESTER_DEFAULT_BATCH_SIZE = 100

OAI_HARVESTER_SORT_OPTIONS: dict[str, Any] = {
    "newest": {
        "title": _("Newest"),
        "fields": ["-created"],
    },
}


OAI_HARVESTER_SEARCH: dict[str, Any] = {
    "facets": [
        "loader",
        "metadata_prefix",
        "setspec",
        "transformers",
        "writers",
    ],
    "sort": ["newest"],
    "sort_default": "newest",
    "sort_default_no_query": "newest",
}

OAI_HARVESTER_FACETS = {
    "loader": {
        "facet": facets.loader,
        "ui": {
            "field": "loader",
        },
    },
    "metadata_prefix": {
        "facet": facets.metadata_prefix,
        "ui": {
            "field": "metadata_prefix",
        },
    },
    "setspec": {
        "facet": facets.setspec,
        "ui": {
            "field": "setspec",
        },
    },
    "transformers": {
        "facet": facets.transformers,
        "ui": {
            "field": "transformers",
        },
    },
    "writers": {
        "facet": facets.writers,
        "ui": {
            "field": "writers",
        },
    },
}


OAI_RECORD_SEARCH: dict[str, Any] = {
    "facets": [
        "harvester",
        "deleted",
        "has_errors",
        "error_code",
        "error_message",
        "error_location",
    ],
    "sort": ["newest"],
    "sort_default": "newest",
    "sort_default_no_query": "newest",
}

OAI_RECORD_FACETS = {
    "harvester": {
        "facet": record_facets.harvester,
        "ui": {
            "field": "harvester",
        },
    },
    "deleted": {
        "facet": record_facets.deleted,
        "ui": {
            "field": "deleted",
        },
    },
    "has_errors": {
        "facet": record_facets.has_errors,
        "ui": {
            "field": "has_errors",
        },
    },
    "error_code": {
        "facet": record_facets.error_code,
        "ui": {
            "field": "error_code",
        },
    },
    "error_message": {
        "facet": record_facets.error_message,
        "ui": {
            "field": "error_message",
        },
    },
    "error_location": {
        "facet": record_facets.error_location,
        "ui": {
            "field": "error_location",
        },
    },
}

OAI_RECORD_SORT_OPTIONS: dict[str, Any] = {
    "newest": {
        "title": _("Newest"),
        "fields": ["-created"],
    },
}
