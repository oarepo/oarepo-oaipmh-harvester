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

import contextlib
import datetime
import json
from typing import TYPE_CHECKING, Any, cast, override

from flask import current_app
from invenio_access.permissions import system_identity
from invenio_db import db
from invenio_db.uow import UnitOfWork
from invenio_pidstore.errors import PersistentIdentifierError
from invenio_records.dictutils import dict_lookup
from invenio_vocabularies.datastreams.writers import BaseWriter
from oarepo_runtime import current_runtime

from oarepo_oaipmh_harvester.oai_record.models import (
    OAIHarvestedRecord,
)
from oarepo_oaipmh_harvester.proxies import current_oai_record_service

if TYPE_CHECKING:
    from collections.abc import Generator

    from flask_principal import Identity
    from invenio_drafts_resources.services.records import (
        RecordService as DraftRecordService,
    )
    from invenio_records_resources.records.api import Record
    from invenio_records_resources.services.records import RecordService
    from invenio_vocabularies.datastreams.datastreams import StreamEntry


# TODO: the writer does not solve the case of dangling draft records
MAX_TRACEBACK_VARIABLE_LENGTH = 100


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
    def write(  # too complex
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
        oai_record = self._get_oai_record(oai_identifier)

        current_app.logger.debug(
            "Processing OAI identifier %s: existing OAI record: %s",
            oai_identifier,
            oai_record,
        )

        # 2. if exists, check if the record is already up to date
        if self._check_up_to_date(stream_entry, oai_record, oai_datestamp, oai_deleted):
            return stream_entry

        pid_value = oai_record.record_pid if oai_record else None
        if not pid_value and not oai_deleted:
            pid_value = self._get_pid_value_from_record(transformed_data)

        # 3. try to get an existing record by pid_value
        existing_record = None
        existing_draft = None
        if pid_value:
            try:
                existing_record = self.service.record_cls.pid.resolve(pid_value)
            except PersistentIdentifierError:
                if self._publish:
                    draft_cls = cast("DraftRecordService", self.service).draft_cls
                    with contextlib.suppress(PersistentIdentifierError):
                        existing_draft = draft_cls.pid.resolve(pid_value)

        # 5. decide on operation type
        op_type = self._determine_operation_type(oai_deleted, existing_record, existing_draft)
        current_app.logger.debug(
            "Determined operation type '%s' for OAI identifier %s (pid_value=%s)",
            op_type,
            oai_identifier,
            pid_value,
        )
        written_data = None
        exception_raised = None

        try:
            written_data = self._save_and_publish_record(
                transformed_data,
                pid_value,
                op_type,
                stream_entry,
                oai_identifier,
            )
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

    def _determine_operation_type(
        self,
        oai_deleted: bool,
        existing_record: Record | None,
        existing_draft: Record | None,
    ) -> str:
        """Determine the operation type based on existing records and deletion status."""
        if oai_deleted:
            if existing_record is not None:
                op_type = "delete"
            elif existing_draft is not None:
                op_type = "delete_draft"
            else:
                op_type = "noop"
        elif existing_record is not None:
            op_type = "update"
        elif existing_draft is not None:
            op_type = "update_draft"
        else:
            op_type = "create"
        return op_type

    def _save_and_publish_record(
        self,
        transformed_data: dict,
        pid_value: str | None,
        op_type: str,
        stream_entry: StreamEntry,
        oai_identifier: str,
    ) -> dict | None:
        """Save and optionally publish a record within a unit of work.

        Args:
            transformed_data: The transformed record data to be saved.
            pid_value: The persistent identifier value of the record.
            op_type: The operation type (create, update, delete, etc.).
            stream_entry: The stream entry being processed.
            oai_identifier: The OAI identifier of the record.

        Returns:
            written_data: The data of the written record, or None if not applicable.

        """
        # we use unit of work here to avoid side effects
        # (such as created draft record) in case of failure
        with UnitOfWork() as uow:
            # resolve lazy strings before writing
            transformed_data = json.loads(json.dumps(transformed_data, default=str))
            try:
                written_data = self._write(transformed_data, pid_value, op_type, uow)
            except Exception:
                current_app.logger.exception(
                    "Error during '%s' operation for OAI identifier %s",
                    op_type,
                    oai_identifier,
                )
                raise
            commit_transaction = True
            if written_data:
                # ensure the written data is also transformed (e.g. to resolve lazy strings)
                written_data = json.loads(json.dumps(written_data, default=str))

                current_app.logger.debug(
                    "Written (%s) %s",
                    op_type,
                    json.dumps(written_data, indent=2, ensure_ascii=False),
                )

                if written_data.get("errors"):
                    # the service reported errors during creation/update

                    stream_entry.errors = [  # type: ignore[reportAttributeAccessIssue]
                        x for err in written_data["errors"] for x in self._convert_to_oai_error(err)
                    ]
                    commit_transaction = False
                elif self._publish and op_type in ("create", "update_draft"):
                    draft_service = cast("DraftRecordService", self.service)
                    draft_service.publish(
                        self._identity,
                        dict_lookup(written_data, self._pid_field),
                        uow=uow,
                    )
            if commit_transaction:
                uow.commit()
            else:
                uow.rollback()
            return written_data

    def _get_oai_record(self, oai_identifier: str) -> OAIHarvestedRecord | None:
        """Get the OAIHarvestedRecord instance by its OAI identifier."""
        return db.session.query(OAIHarvestedRecord).filter_by(oai_identifier=oai_identifier).one_or_none()  # type: ignore[no-any-return]

    def _check_up_to_date(
        self,
        stream_entry: StreamEntry,
        oai_record: OAIHarvestedRecord | None,
        oai_datestamp: datetime.datetime,
        oai_deleted: bool,
    ) -> bool:
        if not oai_record:
            return False

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
                    oai_record.oai_identifier,
                )
                # proceed to re-write the record
            else:
                return True
        return False

    def _get_pid_value_from_record(self, record_data: dict) -> str | None:
        pid_field = getattr(self.service.record_cls.pid, "field", None)
        pid_provider = getattr(pid_field, "_provider", None) if pid_field else None
        get_pid_value_from_record = getattr(pid_provider, "get_pid_value_from_record", None) if pid_provider else None
        pid_type = getattr(pid_field, "_pid_type", None) if pid_field else None
        if get_pid_value_from_record and pid_type:
            # try to get pid value from transformed data
            return get_pid_value_from_record(record_data)  # type: ignore[no-any-return]
        return None

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
        if op_type == "noop":
            return None
        if op_type == "create":
            return cast(
                "dict",
                self.service.create(self._identity, record_data, uow=uow).to_dict(),
            )
        if pid_value is None:
            raise ValueError(f"pid_value must be provided for {op_type} operation")

        if op_type == "update_draft":
            draft_service = cast("DraftRecordService", self.service)
            return cast(
                "dict",
                draft_service.update_draft(self._identity, pid_value, record_data, uow=uow).to_dict(),
            )
        if op_type == "update":
            return cast(
                "dict",
                self.service.update(self._identity, pid_value, record_data, uow=uow).to_dict(),
            )
        if op_type == "delete":
            self.service.delete(self._identity, pid_value, uow=uow)
            return None
        if op_type == "delete_draft":
            draft_service = cast("DraftRecordService", self.service)
            draft_service.delete_draft(self._identity, pid_value, uow=uow)
            return None
        raise ValueError(f"Unknown operation type: {op_type}")

    def write_many(self, stream_entries: list[StreamEntry], *args: Any, **kwargs: Any) -> list[StreamEntry]:
        """Write the input entries using a given service."""
        # For now, just call write() for each entry
        return [self.write(stream_entry, *args, **kwargs) for stream_entry in stream_entries]

    def _convert_exception_to_error_dict(self, exception: Exception) -> dict:
        tb = exception.__traceback__
        formatted_tb = []
        while tb:
            frame = tb.tb_frame
            fn = (frame.f_code.co_filename or "").split("site-packages/")[-1]
            formatted_tb.append(f"{frame.f_code.co_name}@{fn}:{tb.tb_lineno}")
            for local_name, local_value in frame.f_locals.items():
                local_value_str = repr(local_value)
                if len(local_value_str) > MAX_TRACEBACK_VARIABLE_LENGTH:
                    local_value_str = local_value_str[: MAX_TRACEBACK_VARIABLE_LENGTH - 3] + "..."
                formatted_tb.append(f"    {local_name} = {local_value_str}")
            tb = tb.tb_next

        return {
            "type": type(exception).__name__,
            "message": str(exception),
            "location": "\n".join(formatted_tb),
        }

    def _convert_stream_error(self, error: Any) -> dict:
        if isinstance(error, dict):
            return error
        if isinstance(error, Exception):
            return self._convert_exception_to_error_dict(error)
        return {"message": str(error)}

    def _convert_to_oai_error(self, error: Any) -> Generator[dict]:
        """Convert a service error to an OAI-PMH error dict (type, location, message)."""
        if not isinstance(error, dict):
            yield {"message": str(error)}
        else:
            field = error.get("field", "unknown")
            messages = error.get("messages") or []
            for message in messages:
                yield {
                    "type": "validation_error",
                    "location": field,
                    "message": str(message),
                }
