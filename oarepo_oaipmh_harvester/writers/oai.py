import datetime
import traceback
from typing import Any, cast

from flask import current_app
from flask_principal import Identity
from invenio_db import db

from oarepo_oaipmh_harvester.models import OAIHarvestedRecord, OAIHarvesterRun
from oarepo_oaipmh_harvester.proxies import (
    current_oai_record_service,
    current_oai_run_service,
)
from oarepo_oaipmh_harvester.utils import make_safe_json, oai_context, parse_iso_to_utc


class OAIWriter(BaseWriter):
    """
    Writes the oai record and updates the batch status.

    Note: this writer must be called as the last one in the pipeline.
    """

    def __init__(self, *, identity: Identity, **kwargs: Any) -> None:
        super().__init__()
        self._identity = identity

    def write(self, batch: StreamBatch, *args: Any, **kwargs: Any) -> StreamBatch:
        try:
            self.update_oai_records(batch)
        except Exception as e:
            traceback.print_exc()
            raise e
        db.session.commit()

        current_oai_record_service.indexer.bulk_index(
            [
                entry.context["oai"]["identifier"]
                for entry in batch.entries
                if not entry.filtered
            ]
        )

        run = (
            OAIHarvesterRun.query.filter_by(id=batch.context["run_id"])
            .with_for_update()
            .one()
        )
        previously_finished_records = run.finished_records

        run.finished_records += len(batch.entries)
        run.failed_records += len(batch.failed_entries)
        run.ok_records += len(batch.ok_entries)
        run.last_update_time = datetime.datetime.utcnow()

        if batch.last and run.status == "running":
            run.status = "failed" if run.failed_records else "ok"

        if run.status == "ok" and run.failed_records:
            run.status = "failed"

        if run.status != "running":
            run.end_time = run.last_update_time

        db.session.add(run)
        db.session.commit()

        reindex_threshold = current_app.config["OAI_RUN_REINDEX_THRESHOLD"]
        if (
            previously_finished_records // reindex_threshold
            != run.finished_records // reindex_threshold
            or run.status != "running"
        ):
            # Reindex the run
            current_oai_run_service.indexer.bulk_index([run.id])

        return batch

    def update_oai_records(self, batch: StreamBatch):
        for entry in batch.entries:
            if entry.filtered:
                continue

            oai_record_id = oai_context(entry).get("identifier")
            oai_record = OAIHarvestedRecord.query.filter_by(
                oai_identifier=oai_record_id
            ).one_or_none()

            if not oai_record:
                oai_record = OAIHarvestedRecord(
                    oai_identifier=oai_record_id,
                )

            if entry.errors:
                oai_record.has_errors = True
                oai_record.errors = [make_safe_json(err.json) for err in entry.errors]
            else:
                oai_record.has_errors = False
                oai_record.errors = []

            oai_record.harvested_at = datetime.datetime.utcnow()
            oai_record.deleted = entry.deleted
            oai_record.record_id = entry.id
            oai_record.datestamp = parse_iso_to_utc(oai_context(entry)["datestamp"])
            oai_record.original_data = make_safe_json(entry.context["original_data"])
            oai_record.transformed_data = make_safe_json(entry.entry)
            oai_record.run_id = batch.context["run_id"]
            oai_record.title = self._get_entry_title(entry) or oai_record_id

            db.session.add(oai_record)

    @staticmethod
    def _get_entry_title(entry: StreamEntry) -> str | None:
        if entry.entry.get("title"):
            return str(entry.entry["title"])
        metadata: dict[str, Any] = cast(dict[str, Any], entry.entry.get("metadata", {}))
        return metadata.get("title")
