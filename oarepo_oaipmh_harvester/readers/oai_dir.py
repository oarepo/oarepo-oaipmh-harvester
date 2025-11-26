import gzip
from pathlib import Path
from typing import Iterator

import yaml
from invenio_vocabularies.datastreams.readers import BaseReader


class OAIDirReader(BaseReader):
    def __init__(
        self,
        *,
        oai_run=None,
        oai_harvester_id=None,
        manual=False,
        **kwargs,
    ):
        # we are handling url, so ignore the base path
        super().__init__(**kwargs)
        self.oai_run = oai_run
        self.oai_harvester_id = oai_harvester_id
        self.manual = manual

    def __iter__(self) -> Iterator[StreamEntry]:
        parent_dir = Path(self.source)
        files = list(parent_dir.glob("*.yaml.gz"))
        files.sort()
        for f in files:
            with gzip.open(f, "rt") as ff:
                for record in yaml.safe_load(f):
                    yield StreamEntry(
                        record["entry"],
                        context={
                            "oai": record["oai"],
                            "oai_run": self.oai_run,
                            "oai_harvester_id": self.oai_harvester_id,
                            "manual": self.manual,
                        },
                        deleted=record["oai"].get("deleted"),
                    )
