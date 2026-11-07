# SPDX-FileCopyrightText: 2023-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Configuration for OAI-PMH Harvester."""

from __future__ import annotations

from typing import Any

from invenio_i18n import lazy_gettext as _

from oarepo_oaipmh_harvester.oai_harvester import facets
from oarepo_oaipmh_harvester.oai_record import facets as record_facets
from oarepo_oaipmh_harvester.transformers import OAIImportTransformer, SkipIfOwnedTransformer
from oarepo_oaipmh_harvester.writers import OAIServiceWriter

VOCABULARIES_DATASTREAM_TRANSFORMERS = {
    "oai-import": OAIImportTransformer,
    "skip-if-owned": SkipIfOwnedTransformer,
}

VOCABULARIES_DATASTREAM_WRITERS = {
    "oai-service": OAIServiceWriter,
}

# Normally no need to change this value as batch processing is not performed
# in normal transformers and writers and thus higher batch size just means
# higher memory consumption without any performance benefit.
OAI_HARVESTER_DEFAULT_BATCH_SIZE = 1

OAI_HARVESTER_PARALLEL_TARGET_SIZE = 20000
"""Desired number of records in one window of a parallel harvest."""

OAI_HARVESTER_PARALLEL_FIXED_WINDOW = "1d"
"""Window length used when the source does not report how many records a window has."""

OAI_HARVESTER_PARALLEL_MAX_WINDOWS = 2000
"""A parallel harvest never creates more windows than this."""

OAI_HARVESTER_WINDOW_QUEUE: str | None = "low"
"""Celery queue for the window tasks of a parallel harvest; `None` is the default queue.

`low` is the low priority queue of invenio-jobs (`JOBS_QUEUES`), consumed by the workers of
the repositories. The concurrency of the workers consuming it is the number of windows
harvested at the same time - set a dedicated queue to control that independently of other
low priority work.
"""

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
