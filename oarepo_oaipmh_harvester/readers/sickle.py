import datetime
from typing import Iterator

import pytz
from invenio_vocabularies.datastreams.readers import BaseReader
from sickle import Sickle
from sickle.oaiexceptions import NoRecordsMatch

from ..utils import get_oai_datestamp


class SickleReader(BaseReader):
    def __init__(
        self,
        *,
        all_records=None,
        identifiers=None,
        oai_config=None,
        source=None,
        datestamp_from=None,
        datestamp_until=None,
        oai_run=None,
        oai_harvester_id=None,
        manual=False,
        **kwargs,
    ):
        # we are handling url, so ignore the base path
        super().__init__(source=source, base_path=None, **kwargs)
        self.all_records = all_records
        self.identifiers = identifiers
        self.config = oai_config
        if datestamp_from and not isinstance(datestamp_from, str):
            datestamp_from = get_oai_datestamp(datestamp_from)
        if datestamp_until and not isinstance(datestamp_until, str):
            datestamp_until = get_oai_datestamp(datestamp_until)
        self.datestamp_from = datestamp_from
        self.datestamp_until = datestamp_until
        self.oai_run = oai_run
        self.oai_harvester_id = oai_harvester_id
        self.manual = manual

    def __iter__(self) -> Iterator[StreamEntry]:
        request = Sickle(
            self.source, encoding="utf-8", max_retries=50, default_retry_after=60
        )

        dates = {"from": self.datestamp_from, "until": self.datestamp_until}
        setspecs = (self.config["setspecs"] or "").split() or [None]

        for spec in setspecs:
            count = 0

            metadata_prefix = self.config["metadataprefix"] or "oai_dc"
            params = {"metadataPrefix": metadata_prefix}

            params.update(dates)
            if spec:
                params["set"] = spec

            if self.identifiers:

                def record_getter():
                    for identifier in self.identifiers:
                        yield request.GetRecord(
                            identifier=identifier, metadataPrefix=metadata_prefix
                        )

            else:

                def record_getter():
                    yield from request.ListRecords(**params)

            try:
                first_real_datestamp = None
                for record in record_getter():
                    datestamp = record.header.datestamp
                    datestamp = expand_datestamp(datestamp)
                    if first_real_datestamp is None:
                        first_real_datestamp = record.header.datestamp
                    count += 1
                    if (
                        self.config.get("max_records")
                        and count > self.config["max_records"]
                        and record.header.datestamp != first_real_datestamp
                    ):
                        break

                    yield StreamEntry(
                        entry=record.raw,
                        context={
                            "oai": {
                                "metadata": (
                                    record.metadata
                                    if hasattr(record, "metadata")
                                    else {}
                                ),
                                "datestamp": datestamp,
                                "deleted": record.header.deleted,
                                "identifier": record.header.identifier,
                                "setSpecs": record.header.setSpecs,
                                "oai_url": self.source,
                            },
                            "oai_run": self.oai_run,
                            "oai_harvester_id": self.oai_harvester_id,
                            "manual": self.manual,
                        },
                        deleted=record.header.deleted,
                    )

            except NoRecordsMatch:
                continue


def expand_datestamp(datestamp):
    if "T" not in datestamp:
        datestamp += "T00:00:00+00:00"
    elif datestamp.endswith("Z") or datestamp.endswith("z"):
        datestamp = datestamp[:-1] + "+00:00"
    elif "+" not in datestamp:
        datestamp += "+00:00"
    return datetime.datetime.fromisoformat(datestamp).astimezone(pytz.utc).isoformat()
