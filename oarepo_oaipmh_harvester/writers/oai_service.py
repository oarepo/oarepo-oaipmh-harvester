#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Writer for OAI-PMH harvested records using a service."""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any, cast, override

from flask import current_app
from invenio_access.permissions import system_identity
from invenio_db import db
from invenio_db.uow import UnitOfWork
from invenio_records.dictutils import dict_lookup
from invenio_vocabularies.datastreams.writers import BaseWriter
from marshmallow import ValidationError
from oarepo_runtime import current_runtime

from oarepo_oaipmh_harvester.oai_record.models import (
    OAIHarvestedRecord,
)
from oarepo_oaipmh_harvester.proxies import current_oai_record_service

if TYPE_CHECKING:
    from flask_principal import Identity
    from invenio_records_resources.services.records import RecordService
    from invenio_vocabularies.datastreams.datastreams import StreamEntry

# TODO: the writer does not solve the case of dangling draft records


class OAIServiceWriter(BaseWriter):
    """Writer for OAI-PMH harvested records.

    This writer uses a service to write records harvested via OAI-PMH. It also stores
    an OAIRecord model instance to keep track of the harvesting status.
    """

    def __init__(  # noqa PLR0913 too many arguments
        self,
        model: str,
        *args: Any,
        identity: Identity | None = None,
        update_all: bool = False,
        harvester_id: str | None = None,
        pid_field: str = "id",
        publish: bool = True,
        **kwargs: Any,
    ):
        """Initialize the OAI service writer."""
        self._model = model
        self._update_all = update_all
        self._harvester_id = harvester_id
        self._pid_field = pid_field
        self._identity = identity or system_identity
        self._publish = publish

        super().__init__(
            *args,
            **kwargs,
        )

    @property
    def service(self) -> RecordService:
        """Get the service for the specified model."""
        return current_runtime.models[self._model].service

    @override
    def write(  # noqa # too complex
        self,
        stream_entry: StreamEntry,
        *args: Any,
        **kwargs: Any,
    ) -> StreamEntry:
        """Write the input entry using a given service."""
        current_app.logger.debug("Writing entry: %s", stream_entry.entry)
        harvested_at = datetime.datetime.now(datetime.UTC)
        original_data = {"oai_payload": stream_entry.entry["oai_record"].raw}
        transformed_data = stream_entry.entry["record"]

        # 0. extract the record oai identifier
        oai_identifier = stream_entry.entry["oai_record"].header.identifier
        oai_datestamp = stream_entry.entry["oai_record"].header.datestamp
        oai_deleted = stream_entry.entry["oai_record"].header.deleted

        # 1. check if there is an OAI record already
        oai_record = db.session.query(OAIHarvestedRecord).filter_by(oai_identifier=oai_identifier).one_or_none()

        # 2. if so
        pid_value = None
        if oai_record:
            #    2a and datestamp has not changed, skip unless update_all is set
            #       if there were errors during the last harvest, we want to try again
            if (
                oai_datestamp == oai_record.datestamp
                and oai_deleted == oai_record.deleted
                and not self._update_all
                and oai_record.has_errors is False
                and oai_record.has_warnings is False
            ):
                # try to read the existing record
                try:
                    fetched_record = self.service.read(system_identity, oai_record.record_pid)
                    stream_entry.entry["record"] = fetched_record.to_dict()
                except Exception:  # noqa: BLE001 to catch all possible errors
                    current_app.logger.warning(
                        "Failed to read existing record %s for OAI identifier %s. Re-writing the record.",
                        oai_record.record_pid,
                        oai_identifier,
                    )
                    # proceed to re-write the record
                else:
                    return stream_entry

            if oai_record.record_pid is not None:
                pid_value = oai_record.record_pid
                op_type = "update"
            else:
                op_type = "create"
        else:
            op_type = "create"

        # if should delete, set op_type to delete regardless if oai_record exists
        if oai_deleted:
            op_type = "delete"

        written_data = None
        exception_raised = None

        try:
            # we use unit of work here to avoid side effects
            # (such as created draft record) in case of failure
            with UnitOfWork() as uow:
                # resolve lazy strings before writing
                transformed_data = json.loads(json.dumps(transformed_data, default=str))
                written_data = self._write(transformed_data, pid_value, op_type, uow)
                if written_data:
                    # ensure the written data is also transformed (e.g. to resolve lazy strings)
                    written_data = json.loads(json.dumps(written_data, default=str))
                current_app.logger.debug(
                    "Written %s",
                    json.dumps(written_data, indent=2, ensure_ascii=False),
                )

                if written_data and written_data.get("errors"):
                    # the service reported errors during creation/update
                    stream_entry.errors = written_data["errors"]
                    raise ValidationError("Errors during record write operation: " + json.dumps(written_data["errors"]))
                if self._publish and written_data and op_type == "create":
                    publish_method = getattr(self.service, "publish", None)
                    if not publish_method:
                        raise NotImplementedError(f"The service for model {self._model} does not support publishing.")
                    publish_method(
                        self._identity,
                        dict_lookup(written_data, self._pid_field),
                        uow=uow,
                    )
                uow.commit()
        except Exception as e:  # noqa: BLE001 to catch all possible errors
            # we can't know the state of the db connection, rollback is a safe bet
            db.session.rollback()
            exception_raised = e
        finally:
            # In case of exception, the session has been rolled back in the lines
            # above, so we can safely proceed to store the OAI record
            self._store_oai_record(
                oai_record,
                oai_identifier,
                oai_datestamp,
                oai_deleted,
                harvested_at,
                original_data,
                transformed_data,
                stream_entry,
                exception_raised,
                written_data,
            )

        stream_entry.entry = {
            "record": written_data,
            "oai_record": stream_entry.entry["oai_record"],
        }
        stream_entry.op_type = op_type
        return stream_entry

    def _store_oai_record(  # noqa PLR0913 too many arguments
        self,
        oai_record: OAIHarvestedRecord | None,
        oai_identifier: str,
        oai_datestamp: datetime.datetime,
        oai_deleted: bool,
        harvested_at: datetime.datetime,
        original_data: dict,
        transformed_data: dict | None,
        stream_entry: StreamEntry,
        exception_raised: Exception | None,
        written_data: dict | None,
    ):
        """Create or update the OAIHarvestedRecord instance."""
        if not oai_record:
            oai_record = OAIHarvestedRecord(
                oai_identifier=oai_identifier,
                datestamp=oai_datestamp,
                deleted=oai_deleted,
                harvester_id=self._harvester_id,
            )
        # store errors and warnings
        oai_record.errors = [self._convert_stream_error(e) for e in (stream_entry.errors or [])]
        if exception_raised is not None:
            oai_record.errors.append(self._convert_exception_to_error_dict(exception_raised))
        if stream_entry.exc:
            oai_record.errors.append(self._convert_exception_to_error_dict(stream_entry.exc))
        oai_record.harvested_at = harvested_at
        oai_record.has_errors = bool(oai_record.errors)
        # no warnings tracking for now
        oai_record.has_warnings = False

        # store the internal identifier
        # written_entry.entry is a RecordItem from the service, not plain record
        if written_data is not None:
            pid = dict_lookup(written_data, self._pid_field)
            oai_record.record_pid = pid
            oai_record.record_type = self._model

        # store the original and transformed data
        oai_record.original_data = original_data
        oai_record.transformed_data = transformed_data or {}

        db.session.add(oai_record)
        db.session.commit()

        current_oai_record_service.indexer.bulk_index([oai_record.oai_identifier])

    def _write(self, record_data: dict, pid_value: str | None, op_type: str, uow: UnitOfWork) -> dict | None:
        """Write the record data using the service."""
        if op_type == "create":
            return cast(
                "dict",
                self.service.create(self._identity, record_data, uow=uow).to_dict(),
            )
        if op_type == "update":
            if pid_value is None:
                raise ValueError("pid_value must be provided for update operation")
            try:
                return cast(
                    "dict",
                    self.service.update(self._identity, pid_value, record_data, uow=uow).to_dict(),
                )
            except Exception:  # noqa BLE001 to catch all possible errors
                # if update fails, try to update draft
                try:
                    update_draft = getattr(self.service, "update_draft", None)
                    if update_draft is None:
                        raise NotImplementedError(f"The service for model {self._model} does not support draft update.")
                    return cast(
                        "dict",
                        update_draft(self._identity, pid_value, record_data, uow=uow).to_dict(),
                    )
                except Exception:  # noqa BLE001 to catch all possible errors
                    # if draft update also fails, try to create new record
                    return self._write(record_data, pid_value, "create", uow)

        if op_type == "delete":
            if pid_value is not None:
                self.service.delete(self._identity, pid_value, uow=uow)
            return None
        raise ValueError(f"Unknown operation type: {op_type}")

    def write_many(self, stream_entries: list[StreamEntry], *args: Any, **kwargs: Any) -> list[StreamEntry]:
        """Write the input entries using a given service."""
        # For now, just call write() for each entry
        return [self.write(stream_entry, *args, **kwargs) for stream_entry in stream_entries]

    def _convert_exception_to_error_dict(self, exception: Exception) -> dict:
        return {
            "type": type(exception).__name__,
            "message": str(exception),
        }

    def _convert_stream_error(self, error: Any) -> dict:
        if isinstance(error, dict):
            return error
        if isinstance(error, Exception):
            return self._convert_exception_to_error_dict(error)
        return {"message": str(error)}
