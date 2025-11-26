from typing import Any

from invenio_i18n import lazy_gettext as _
from invenio_vocabularies.datastreams.readers import BaseReader
from invenio_vocabularies.datastreams.transformers import BaseTransformer
from invenio_vocabularies.datastreams.writers import BaseWriter

from oarepo_oaipmh_harvester.oai_record import facets as record_facets
from oarepo_oaipmh_harvester.oai_run import facets as run_facets
from oarepo_oaipmh_harvester.permissions import OAIHarvesterPermissions
from oarepo_oaipmh_harvester.readers.oai_dir import OAIDirReader
from oarepo_oaipmh_harvester.readers.sickle import SickleReader
from oarepo_oaipmh_harvester.transformers.marcxml import MarcXMLTransformer
from oarepo_oaipmh_harvester.transformers.original_data import (
    OriginalDataTransformer,
)
from oarepo_oaipmh_harvester.transformers.record_lookup import (
    OAIRecordLookupTransformer,
)
from oarepo_oaipmh_harvester.writers.oai import OAIWriter
from oarepo_oaipmh_harvester.writers.oai_dir import OAIDirWriter

DATASTREAMS_READERS: dict[str, type[BaseReader]] = {
    "sickle": SickleReader,
    "oai_dir": OAIDirReader,
}

DATASTREAMS_TRANSFORMERS: dict[str, type[BaseTransformer]] = {
    "marcxml": MarcXMLTransformer,
    "oai_record_lookup": OAIRecordLookupTransformer,
    "set_original_data": OriginalDataTransformer,
}

DATASTREAMS_WRITERS: dict[str, type[BaseWriter]] = {
    "oai_dir": OAIDirWriter,
    "oai": OAIWriter,
}

OAREPO_PERMISSIONS_PRESETS = {"oai_harvester": OAIHarvesterPermissions}


OAI_RUN_SEARCH: dict[str, Any] = {
    "facets": [
        "harvester",
        "harvester_name",
        "manual",
        "status",
    ],
    "sort": ["newest"],
    "sort_default": "newest",
    "sort_default_no_query": "newest",
}

OAI_RUN_FACETS = {
    "harvester": {
        "facet": run_facets.harvester,
        "ui": {
            "field": "harvester",
        },
    },
    "harvester_name": {
        "facet": run_facets.harvester_name,
        "ui": {
            "field": "harvester_name",
        },
    },
    "manual": {
        "facet": run_facets.manual,
        "ui": {
            "field": "manual",
        },
    },
    "status": {
        "facet": run_facets.status,
        "ui": {
            "field": "status",
        },
    },
}
OAI_RUN_SORT_OPTIONS: dict[str, Any] = {
    "newest": dict(
        title=_("Newest"),
        fields=["-created"],
    ),
}

OAI_RUN_REINDEX_THRESHOLD = 100
"""Reindex OAI run after this many records from the previous reindex."""

OAI_HARVESTER_SORT_OPTIONS: dict[str, Any] = {
    "newest": dict(
        title=_("Newest"),
        fields=["-created"],
    ),
}

from oarepo_oaipmh_harvester.oai_harvester.services.records import facets

OAI_HARVESTER_SEARCH: dict[str, Any] = {
    "facets": [
        "batch_size",
        "harvest_managers_id",
        "harvest_managers_email",
        "loader",
        "max_records",
        "metadataprefix",
        "setspecs",
        "transformers",
        "writers",
    ],
    "sort": ["newest"],
    "sort_default": "newest",
    "sort_default_no_query": "newest",
}

OAI_HARVESTER_FACETS = {
    "batch_size": {
        "facet": facets.batch_size,
        "ui": {
            "field": "batch_size",
        },
    },
    "harvest_managers_id": {
        "facet": facets.harvest_managers_id,
        "ui": {
            "field": "harvest_managers_id",
        },
    },
    "harvest_managers_email": {
        "facet": facets.harvest_managers_email,
        "ui": {
            "field": "harvest_managers_email",
        },
    },
    "loader": {
        "facet": facets.loader,
        "ui": {
            "field": "loader",
        },
    },
    "max_records": {
        "facet": facets.max_records,
        "ui": {
            "field": "max_records",
        },
    },
    "metadataprefix": {
        "facet": facets.metadataprefix,
        "ui": {
            "field": "metadataprefix",
        },
    },
    "setspecs": {
        "facet": facets.setspecs,
        "ui": {
            "field": "setspecs",
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
    "newest": dict(
        title=_("Newest"),
        fields=["-created"],
    ),
}
