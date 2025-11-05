from oarepo_runtime.services.search import SearchOptions

from . import facets


class OaiHarvesterSearchOptions(SearchOptions):
    """OaiHarvesterRecord search options."""

    facet_groups = {}

    facets = {
        "code": facets.code,
        "batch_size": facets.batch_size,
        "harvest_managers_id": facets.harvest_managers_id,
        "harvest_managers_email": facets.harvest_managers_email,
        "loader": facets.loader,
        "max_records": facets.max_records,
        "metadataprefix": facets.metadataprefix,
        "setspecs": facets.setspecs,
        "transformers": facets.transformers,
        "writers": facets.writers,
        **getattr(SearchOptions, "facets", {}),
    }
