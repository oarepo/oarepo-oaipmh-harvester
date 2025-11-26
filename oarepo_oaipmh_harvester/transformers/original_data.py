import copy
import logging
from typing import Any

from oarepo_oaipmh_harvester.utils import oai_context

log = logging.getLogger("oaipmh.harvest")


class OriginalDataTransformer(BaseTransformer):
    """
    Sets original data.
    """

    def __init__(
        self,
        **kwargs: Any,
    ):
        super().__init__()

    def apply(self, batch: StreamBatch, *args: Any, **kwargs: Any) -> StreamBatch:
        for entry in batch.entries:
            log.info(
                "OAI identifer: %s, datestamp %s, deleted %s",
                oai_context(entry).get("identifier"),
                oai_context(entry).get("datestamp"),
                oai_context(entry).get("deleted"),
            )
            if isinstance(entry.entry, dict):
                entry.context["original_data"] = copy.deepcopy(entry.entry)
            else:
                entry.context["original_data"] = {"data": copy.deepcopy(entry.entry)}
        return batch
