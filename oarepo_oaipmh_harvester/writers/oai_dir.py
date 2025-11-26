import datetime
import gzip
from pathlib import Path

import yaml


class OAIDirWriter(BaseWriter):
    def __init__(self, *, dir, **kwargs) -> None:
        super().__init__()
        self.target = dir

    def write_batch(self, batch: StreamBatch, *args, **kwargs):
        entries = [x for x in batch.entries if x.ok]
        if not entries:
            return batch
        dn = Path(self.target)
        if not dn.exists():
            dn.mkdir(parents=True)
        fn = datetime.datetime.now().isoformat().replace(":", "-")
        with gzip.open(dn / f"{fn}.yaml.gz", "wt") as f:
            yaml.safe_dump(_serialize_entries(entries), f, allow_unicode=True)
        return batch
