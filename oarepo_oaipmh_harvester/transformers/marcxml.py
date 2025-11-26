from collections import defaultdict

from dojson.contrib.marc21.utils import GroupableOrderedDict, create_record
from lxml import etree


class MarcXMLTransformer(BaseTransformer):
    def __init__(self, **kwargs) -> None:
        super().__init__()

    def apply(self, batch: StreamBatch, *args, **kwargs) -> StreamBatch:
        for entry in batch.entries:
            self.apply_entry(entry, *args, **kwargs)
        return batch

    def apply_entry(self, stream_entry: StreamEntry, *args, **kwargs) -> StreamEntry:
        xml = etree.fromstring(stream_entry.entry)
        ret = {}
        for k, vals in create_record(xml).items():
            if k == "__order__":
                continue
            if isinstance(vals, GroupableOrderedDict):
                for kk, v in vals.items():
                    if kk == "__order__":
                        continue
                    ret[k + kk] = v
            elif isinstance(vals, tuple):
                lret = defaultdict(list)
                for idx, vval in enumerate(vals):
                    for kk, v in vval.items():
                        if kk == "__order__":
                            continue
                        if (k + kk) not in lret and idx:
                            lret[k + kk] = [None] * idx
                        lret[k + kk].append(v)
                    for v in lret.values():
                        if len(v) <= idx:
                            v.append(None)

                ret.update({k: tuple(v) for k, v in lret.items()})
            else:
                ret[k] = vals
        stream_entry.entry = ret
        stream_entry.context["marcxml_parsed"] = ret
        return stream_entry
