# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""`skip-if-owned` transformer - lets a fallback harvester give way to other harvesters.

Datastream configuration: `skip-if-owned{model:"<model>"}`.

Put it last in the transformer chain of a harvester that should write a record only when
no other harvester writes the same local record, e.g. a DataCite harvester next to
the harvesters of the repositories that registered the DOIs. Both harvesters must produce
the same local pid for the same record (e.g. `doi/<doi>`).

The entry is marked as filtered (and so skipped by the `oai-service` writer, see
[OAIServiceWriter][oarepo_oaipmh_harvester.writers.oai_service.OAIServiceWriter]) when
another harvester owns the local pid - it has a harvest record of the same model and pid
that is not deleted at its source and whose last write was not skipped. The local pid is
taken from the harvest record of the entry, or from the transformed data via the pid
provider's `get_pid_value_from_record`, like the writer does.

Every scenario resolves to the owner's data:

- the other harvester comes first - the entry is skipped, also when it is deleted at
  the source (the owner's record is not deleted);
- this harvester comes first - its record is overwritten by the other harvester, later
  harvests of the entry are skipped;
- the other harvester's record is deleted at its source - the entry is written again the
  next time it is harvested (skipped entries are never up to date), restoring the record
  with this harvester's data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from invenio_db import db
from invenio_vocabularies.datastreams.transformers import BaseTransformer
from oarepo_runtime import current_runtime

from oarepo_oaipmh_harvester.oai_record.models import OAIHarvestedRecord
from oarepo_oaipmh_harvester.writers.oai_service import SKIP_REASON, get_pid_value_from_record

if TYPE_CHECKING:
    from invenio_vocabularies.datastreams.datastreams import StreamEntry


class SkipIfOwnedTransformer(BaseTransformer):
    """Mark the entry as filtered if another harvester owns its local record."""

    def __init__(
        self,
        model: str,
        *_args: Any,
        harvester_id: str,
        **_kwargs: Any,
    ) -> None:
        """Initialize the transformer.

        Args:
            model: Name of the target model (`current_runtime.models`).
            harvester_id: Harvester the entries belong to (set by the harvest task).

        """
        super().__init__()
        self._model = model
        self._harvester_id = harvester_id

    @override
    def apply(self, stream_entry: StreamEntry, *_args: Any, **_kwargs: Any) -> StreamEntry:
        """Mark the entry as filtered, with the reason in `entry["skip_reason"]`, if the pid is owned."""
        oai_identifier = stream_entry.entry["oai_record"].header.identifier
        pid_value = self._pid_value(oai_identifier, stream_entry.entry.get("record"))
        if not pid_value:
            return stream_entry

        owner = (
            db.session.query(OAIHarvestedRecord.harvester_id, OAIHarvestedRecord.oai_identifier)
            .filter(
                OAIHarvestedRecord.harvester_id != self._harvester_id,
                OAIHarvestedRecord.record_type == self._model,
                OAIHarvestedRecord.record_pid == pid_value,
                OAIHarvestedRecord.deleted.is_(False),
                # a skipped harvest record does not own the pid - two fallback harvesters
                # would otherwise skip each other's records forever
                OAIHarvestedRecord.has_warnings.is_(False),
            )
            .first()
        )
        if owner is not None:
            stream_entry.filtered = True
            stream_entry.entry[SKIP_REASON] = (
                f"Record {pid_value} is harvested by harvester {owner.harvester_id} ({owner.oai_identifier})"
            )
        return stream_entry

    def _pid_value(self, oai_identifier: str, record_data: dict | None) -> str | None:
        """Local pid of the entry - from its harvest record, or from the transformed data."""
        record_pid = db.session.query(OAIHarvestedRecord.record_pid).filter_by(oai_identifier=oai_identifier).scalar()
        if record_pid:
            return record_pid
        if not record_data:
            # deleted at the source and never written - nothing to protect
            return None
        return get_pid_value_from_record(current_runtime.models[self._model].service, record_data)
