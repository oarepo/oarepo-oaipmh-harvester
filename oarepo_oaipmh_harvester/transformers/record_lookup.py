from typing import Any, Generator, cast

from flask_principal import Identity
from invenio_records_resources.proxies import current_service_registry  # type: ignore

from oarepo_oaipmh_harvester.models import OAIHarvestedRecord
from oarepo_oaipmh_harvester.utils import oai_context, parse_iso_to_utc


def dict_lookup_ignore_arrays(
    source: Any, lookup_key: list[str]
) -> Generator[Any, None, None]:
    if not lookup_key:
        yield source
    else:
        if isinstance(source, list):
            for item in cast(list[Any], source):
                yield from dict_lookup_ignore_arrays(item, lookup_key)
        elif isinstance(source, dict) and lookup_key[0] in source:
            yield from dict_lookup_ignore_arrays(source[lookup_key[0]], lookup_key[1:])


class OAIRecordLookupTransformer(BaseTransformer):
    """
    Looks up target records and oai records for the given batch and filters out
    the records that have the same datestamp and have been harvested successfully
    during the previous harvest.

    If there was a previous harvest error, the oai record id is stored in the
    batch entry context so that it can be deleted later in oai writer
    """

    def __init__(
        self,
        identity: Identity,
        oai_identifier_field: str = "oai.harvest.identifier",
        oai_datestamp_field: str = "oai.harvest.datestamp",
        oai_identifier_facet: str | None = None,
        oai_datestamp_facet: str | None = None,
        harvested_record_service: str | None = None,
        overwrite_all_records: bool = False,
        **kwargs: Any,
    ):
        super().__init__()
        assert (
            harvested_record_service is not None
        ), "Harvested record service must be set for record lookup transformer"
        self._identity = identity
        self._oai_identifier_field = oai_identifier_field.split(".")
        self._oai_datestamp_field = oai_datestamp_field.split(".")
        self._oai_identifier_facet = (
            oai_identifier_facet or oai_identifier_field.replace(".", "_")
        )
        self._oai_datestamp_facet = oai_datestamp_facet or oai_datestamp_field.replace(
            ".", "_"
        )
        self._harvested_record_service = current_service_registry.get(
            harvested_record_service
        )
        self._overwrite_all_records = overwrite_all_records

    def apply(self, batch: StreamBatch, *args: Any, **kwargs: Any) -> StreamBatch:
        by_oai_identifier: dict[str, StreamEntry] = {
            oai_context(entry)["identifier"]: entry for entry in batch.entries
        }
        if not by_oai_identifier:
            return batch

        self.copy_harvest_metadata_to_entries(batch)
        self.filter_successfully_harvested_records(by_oai_identifier)

        return batch

    def copy_harvest_metadata_to_entries(self, batch: StreamBatch):
        for entry in batch.entries:
            entry_oai: dict[str, Any] = cast(
                dict[str, Any], entry.entry.setdefault("oai", {})
            )
            harvest_metadata: dict[str, str] = entry_oai.setdefault("harvest", {})

            harvest_metadata["datestamp"] = oai_context(entry)["datestamp"]
            harvest_metadata["identifier"] = oai_context(entry)["identifier"]

    def filter_successfully_harvested_records(
        self, by_oai_identifier: dict[str, StreamEntry]
    ):
        """
        Filters out the records that have been harvested successfully during the previous harvest
        if they have not been modified since then.

        :param by_oai_identifier: the batch entries indexed by oai identifier
        """
        # these are the records that have been harvested successfully during the previous harvest
        previously_harvested = OAIHarvestedRecord.query.filter(
            OAIHarvestedRecord.oai_identifier.in_(list(by_oai_identifier.keys())),
            OAIHarvestedRecord.deleted.is_(False),
            OAIHarvestedRecord.record_id.isnot(None),
        ).all()

        for harvested_record in previously_harvested:
            oai_identifier = harvested_record.oai_identifier

            entry = by_oai_identifier[oai_identifier]
            entry.entry["id"] = harvested_record.record_id
            entry.id = harvested_record.record_id

            datestamp = harvested_record.datestamp

            if not self._overwrite_all_records and datestamp >= parse_iso_to_utc(
                oai_context(entry)["datestamp"]
            ):
                # do not save the item as it has the same datestamp
                entry.filtered = True
