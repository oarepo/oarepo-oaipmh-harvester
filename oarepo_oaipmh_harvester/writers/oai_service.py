# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""`oai-service` writer - synchronizes local records with harvested ones.

Datastream configuration: `oai-service{model:"<model>", ...}`, see
[OAIServiceWriter][oarepo_oaipmh_harvester.writers.oai_service.OAIServiceWriter] for the
options.

Entries that failed to be transformed (`errors` / `exc` set, see
[CatchingTransformer][oarepo_oaipmh_harvester.datastream.CatchingTransformer]) are not written - only
their errors are stored on the harvest record, the local record is left as it is.

For each harvested entry the writer

1. loads the harvest record
   ([OAIHarvestedRecord][oarepo_oaipmh_harvester.oai_record.models.OAIHarvestedRecord]) of
   the OAI identifier; the local pid is taken from it, or - for a record harvested for the
   first time - from the transformed data via the pid provider's `get_pid_value_from_record`
   (records deposited locally with the same pid are taken over);
2. classifies the local record -
   [LocalRecord.resolve][oarepo_oaipmh_harvester.writers.oai_service.LocalRecord.resolve]
   returns a [LocalState][oarepo_oaipmh_harvester.writers.oai_service.LocalState] (absent,
   live, draft only, tombstoned, hard deleted) together with the record and a local draft,
   if any;
3. picks the [Operation][oarepo_oaipmh_harvester.writers.oai_service.Operation] that brings
   the local record to the harvested state -
   [LocalRecord.operation][oarepo_oaipmh_harvester.writers.oai_service.LocalRecord.operation].
   The harvest always wins: locally deleted records are restored (rdm tombstones,
   `restore_record`) or revived (hard deleted records are reverted to their last revision,
   keeping the pid), locally restored records are deleted again, local edit drafts are
   overwritten or removed;
4. skips the entry if the OAI datestamp and deleted flag are unchanged, the last write had
   no errors and the local record is already in the harvested state;
5. executes the operation inside a unit of work (multi-step operations such as restore +
   update roll back together) and publishes drafts where needed;
6. stores the harvest record with the datestamp, transformed data, local pid and errors.

Draft services do not allow updating published records, so updates go through edit -
update draft - publish unless `direct_update` is set. Records of rdm services are deleted
with `delete_record` (tombstone with a note about the deletion at the source), other
services with `delete`.

Written records are added to the `community` writer option (slug or id) and to the
communities listed by the transformer in `parent.communities.ids` of the transformed data.
They are added directly (rdm `bulk_add`), without a community inclusion request; communities
the record is already in are skipped, and the record is never removed from a community.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast, override

from flask import current_app
from invenio_access.permissions import system_identity
from invenio_communities.proxies import current_communities
from invenio_db import db
from invenio_db.uow import UnitOfWork
from invenio_pidstore.errors import PersistentIdentifierError, PIDDeletedError
from invenio_pidstore.models import PersistentIdentifier, PIDStatus
from invenio_rdm_records.proxies import current_rdm_records
from invenio_rdm_records.records.systemfields.deletion_status import RecordDeletionStatusEnum
from invenio_records.dictutils import dict_lookup
from invenio_records_resources.services.uow import RecordIndexOp
from invenio_vocabularies.datastreams.writers import BaseWriter
from oarepo_runtime import current_runtime
from sqlalchemy.exc import NoResultFound

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
    from invenio_rdm_records.records.api import RDMRecord
    from invenio_rdm_records.services.services import RDMRecordService
    from invenio_records_resources.records.api import Record
    from invenio_records_resources.services.records import RecordService
    from invenio_vocabularies.datastreams.datastreams import StreamEntry


MAX_TRACEBACK_VARIABLE_LENGTH = 100


def _utc_datestamp(datestamp: str | dt.datetime) -> dt.datetime:
    """Parse an OAI datestamp into an aware UTC datetime, as stored in the db column.

    The header datestamp is a string (`2025-01-01` or `2025-01-01T00:00:00Z`); without
    parsing it never equals the stored value and every harvest re-writes every record.
    OAI-PMH datestamps are always UTC, so a value without timezone is taken as UTC.
    """
    if isinstance(datestamp, str):
        datestamp = dt.datetime.fromisoformat(datestamp)
    if datestamp.tzinfo is None:
        return datestamp.replace(tzinfo=dt.UTC)
    return datestamp.astimezone(dt.UTC)


class LocalState(StrEnum):
    """State of the local record that corresponds to a harvested OAI record."""

    ABSENT = "absent"
    """No local record nor draft."""

    LIVE = "live"
    """Published, not deleted record (or a plain record for models without drafts)."""

    DRAFT_ONLY = "draft_only"
    """No published record (or a hard deleted one), but a draft exists."""

    TOMBSTONED = "tombstoned"
    """RDM record soft-deleted via `delete_record` (deletion status `D` or `X`)."""

    HARD_DELETED = "hard_deleted"
    """Record deleted via `service.delete` - `model.is_deleted` set, pid status `D`."""


class Operation(StrEnum):
    """Operation that brings the local record to the state reported by the OAI-PMH source."""

    NOOP = "noop"
    CREATE = "create"
    UPDATE = "update"
    """Update a live record (for draft services: edit, update draft, publish - unless `direct_update`)."""
    UPDATE_DRAFT = "update_draft"
    RESTORE = "restore"
    """Restore a tombstoned rdm record (unmarking it from purge if needed), then update it."""
    REVIVE = "revive"
    """Revert a hard deleted record to its last revision, re-register its pid, then update it."""
    DELETE = "delete"
    """Delete via `service.delete` - for services without rdm deletion workflow."""
    DELETE_RECORD = "delete_record"
    """Tombstone via rdm `delete_record`."""
    DELETE_DRAFT = "delete_draft"


@dataclass(frozen=True)
class LocalRecord:
    """Local record state together with the resolved record and draft (if any)."""

    state: LocalState
    pid_value: str | None = None
    is_rdm: bool = False
    """Service supports rdm deletion workflow (tombstones via `delete_record`)."""
    record: Record | None = None
    draft: Record | None = None
    deleted_pid: PersistentIdentifier | None = None
    """Pid of a hard deleted record (status `D`)."""

    @classmethod
    def resolve(cls, service: RecordService, pid_value: str | None, *, with_drafts: bool) -> LocalRecord:
        """Find the local record (and draft) for the pid value and classify its state."""
        is_rdm = hasattr(service, "delete_record")
        if not pid_value:
            return cls(LocalState.ABSENT, pid_value, is_rdm)

        record_cls = service.record_cls
        record = None
        deleted_pid = None
        state = LocalState.ABSENT
        try:
            record = record_cls.pid.resolve(pid_value)
        except PIDDeletedError as e:
            # hard (non-tombstone) delete: the resolver does not return the record,
            # so load it including deleted ones
            state = LocalState.HARD_DELETED
            deleted_pid = e.pid
            if e.pid.object_uuid:
                with contextlib.suppress(NoResultFound):
                    record = record_cls.get_record(e.pid.object_uuid, with_deleted=True)
        except PersistentIdentifierError, NoResultFound:
            # NoResultFound: rdm draft-only record - pid points to the draft, not to a record
            pass
        else:
            deletion_status = getattr(record, "deletion_status", None)
            if deletion_status is not None and deletion_status.is_deleted:
                state = LocalState.TOMBSTONED
            else:
                state = LocalState.LIVE

        draft = None
        if with_drafts:
            draft_cls = cast("DraftRecordService", service).draft_cls
            # registered_only=False - drafts that were never published have a NEW pid;
            # the soft-deleted draft of a published record does not resolve
            with contextlib.suppress(PersistentIdentifierError, NoResultFound):
                draft = draft_cls.pid.resolve(pid_value, registered_only=False)
        if draft is not None and state in (LocalState.ABSENT, LocalState.HARD_DELETED):
            state = LocalState.DRAFT_ONLY
        return cls(state, pid_value, is_rdm, record, draft, deleted_pid)

    def operation(self, oai_deleted: bool) -> Operation:  # noqa PLR0911
        """Determine the operation that brings the local record to the harvested state.

        The harvest always wins - whatever happened to the record locally, the state
        reported by the OAI-PMH source becomes the local state.
        """
        if oai_deleted:
            match self.state:
                case LocalState.LIVE:
                    return Operation.DELETE_RECORD if self.is_rdm else Operation.DELETE
                case LocalState.DRAFT_ONLY:
                    return Operation.DELETE_DRAFT
                case LocalState.TOMBSTONED if self.draft is not None:
                    # deleted locally, but a local edit draft survived
                    return Operation.DELETE_DRAFT
                case _:
                    # already deleted locally (tombstoned / hard deleted) or never existed
                    return Operation.NOOP
        match self.state:
            case LocalState.LIVE:
                return Operation.UPDATE
            case LocalState.DRAFT_ONLY:
                return Operation.UPDATE_DRAFT
            case LocalState.TOMBSTONED:
                return Operation.RESTORE
            case LocalState.HARD_DELETED if self.record is not None and self.deleted_pid is not None:
                return Operation.REVIVE
            case _:
                return Operation.CREATE


class OAIServiceWriter(BaseWriter):
    """Writer for OAI-PMH harvested records.

    This writer uses a service to write records harvested via OAI-PMH. It also stores
    an OAIRecord model instance to keep track of the harvesting status.
    """

    def __init__(  # noqa PLR0913,PLR0917
        self,
        model: str,
        *args: Any,
        identity: Identity | None = None,
        update_all: bool = False,
        harvester_id: str | None = None,
        pid_field: str = "id",
        publish: bool = True,
        direct_update: bool = False,
        community: str | None = None,
        **kwargs: Any,
    ):
        """Initialize the OAI service writer.

        Args:
            model: Name of the target model (`current_runtime.models`).
            identity: Identity used for the service calls, defaults to the system identity.
            update_all: Write every record, even if it is up to date.
            harvester_id: Harvester the harvest records belong to (set by the harvest task).
            pid_field: Path of the pid value in the service result.
            publish: Publish created / updated drafts. Required (`ValueError` otherwise) for
                rdm models; `False` only for models without drafts.
            direct_update: Update published records via `service.update` instead of edit -
                update draft - publish. Only for services that allow updating published
                records (drafts services do not by default).
            community: Slug (or id) of a community every written record is added to. Only
                for rdm models.

        """
        self._model = model
        self._update_all = update_all
        self._harvester_id = harvester_id
        self._pid_field = pid_field
        self._identity = identity or system_identity
        self._publish = publish
        self._direct_update = direct_update
        self._community = community

        super().__init__(
            *args,
            **kwargs,
        )

        is_rdm = hasattr(self.service, "delete_record")
        if not publish and is_rdm:
            # rdm records can not be updated directly, only via edit - update draft - publish
            raise ValueError(f"Model '{model}' uses rdm records service, the oai-service writer needs publish=True.")
        if community and not is_rdm:
            raise ValueError(f"Model '{model}' does not use rdm records service, it can not be added to communities.")

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
        harvested_at = dt.datetime.now(dt.UTC)
        original_data = {"oai_payload": stream_entry.entry["oai_record"].raw}
        transformed_data = stream_entry.entry["record"]

        # 0. extract the record oai identifier
        oai_identifier = stream_entry.entry["oai_record"].header.identifier
        oai_datestamp = _utc_datestamp(stream_entry.entry["oai_record"].header.datestamp)
        oai_deleted = stream_entry.entry["oai_record"].header.deleted

        # 1. check if there is an OAI record already
        oai_record = self._get_oai_record(oai_identifier)

        current_app.logger.debug(
            "Processing OAI identifier %s: existing OAI record: %s",
            oai_identifier,
            oai_record,
        )

        written_data = None
        validation_errors: list[dict] = []
        exception_raised = None
        op_type = None

        try:
            if stream_entry.errors or stream_entry.exc is not None:
                # reading / transformation failed - only the errors are stored on the oai
                # record, the local record is left as it is
                current_app.logger.debug("Not writing OAI identifier %s, it has errors", oai_identifier)
            else:
                pid_value = oai_record.record_pid if oai_record else None
                if not pid_value and not oai_deleted:
                    pid_value = self._get_pid_value_from_record(transformed_data)

                # 2. find out the state of the local record
                local = LocalRecord.resolve(self.service, pid_value, with_drafts=self._publish)

                # 3. decide on operation type
                op_type = local.operation(oai_deleted)

                # 4. if exists, check if the record is already up to date
                if self._check_up_to_date(stream_entry, oai_record, oai_datestamp, oai_deleted, local):
                    return stream_entry
                current_app.logger.debug(
                    "Determined operation type '%s' for OAI identifier %s (pid_value=%s, local state=%s)",
                    op_type,
                    oai_identifier,
                    pid_value,
                    local.state,
                )

                written_data, validation_errors = self._save_and_publish_record(
                    transformed_data,
                    local,
                    op_type,
                    oai_identifier,
                )
        except Exception as e:  # noqa BLE001 ok to catch here
            # we can't know the state of the db connection, rollback is a safe bet
            db.session.rollback()
            exception_raised = e

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
            validation_errors,
            exception_raised,
            written_data,
        )

        # the datastream api expects error messages; structured errors are on the oai record
        stream_entry.errors = [
            *(stream_entry.errors or []),
            *(f"{error.get('location', '')}: {error['message']}" for error in validation_errors),
        ]
        stream_entry.entry = {
            "record": written_data,
            "oai_record": stream_entry.entry["oai_record"],
        }
        stream_entry.op_type = op_type
        return stream_entry

    def _save_and_publish_record(
        self,
        transformed_data: dict,
        local: LocalRecord,
        op_type: Operation,
        oai_identifier: str,
    ) -> tuple[dict | None, list[dict]]:
        """Save and optionally publish a record within a unit of work.

        Args:
            transformed_data: The transformed record data to be saved.
            local: The local record (state, pid value) the operation is applied to.
            op_type: The operation type (create, update, delete, etc.).
            oai_identifier: The OAI identifier of the record.

        Returns:
            written_data: The data of the written record, or None if not applicable.
            validation_errors: Errors reported by the service (`type`, `location`,
                `message`); the transaction is rolled back if there are any.

        """
        # we use unit of work here to avoid side effects
        # (such as created draft record) in case of failure
        with UnitOfWork() as uow:
            # resolve lazy strings before writing
            transformed_data = json.loads(json.dumps(transformed_data, default=str))
            # parent communities are not writable via the service, they are added after publishing
            communities = self._pop_communities(transformed_data)
            try:
                written_data = self._write(transformed_data, local, op_type, oai_identifier, uow)
            except Exception:
                current_app.logger.exception(
                    "Error during '%s' operation for OAI identifier %s",
                    op_type,
                    oai_identifier,
                )
                raise
            commit_transaction = True
            validation_errors: list[dict] = []
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

                    validation_errors = [x for err in written_data["errors"] for x in self._convert_to_oai_error(err)]
                    commit_transaction = False
                elif self._publish and (
                    op_type in (Operation.CREATE, Operation.UPDATE_DRAFT)
                    or (
                        # with direct update the published record is updated, no draft to publish
                        not self._direct_update and op_type in (Operation.UPDATE, Operation.RESTORE, Operation.REVIVE)
                    )
                ):
                    draft_service = cast("DraftRecordService", self.service)
                    draft_service.publish(
                        self._identity,
                        dict_lookup(written_data, self._pid_field),
                        uow=uow,
                    )
                if commit_transaction:
                    self._add_to_communities(dict_lookup(written_data, self._pid_field), communities, uow)
            if commit_transaction:
                uow.commit()
            else:
                uow.rollback()
            return written_data, validation_errors

    def _pop_communities(self, record_data: dict | None) -> list[str]:
        """Remove `parent.communities` from the record data, return the writer's and the listed communities."""
        # no record data for records deleted at the source
        parent = (record_data or {}).get("parent") or {}
        listed = (parent.pop("communities", None) or {}).get("ids") or []
        # dict.fromkeys - remove duplicates, keep the order
        return list(dict.fromkeys([*([self._community] if self._community else []), *listed]))

    def _add_to_communities(self, pid_value: str, communities: list[str], uow: UnitOfWork) -> None:
        """Add the published record to the communities (slugs or ids) it is not in yet.

        `bulk_add` adds the record directly, without an inclusion request (allowed for system
        processes only), also adds a subcommunity's parent and makes the community the default
        one when the record has none.
        """
        for community in communities:
            # resolved for each community - adding a subcommunity also adds its parent
            record = cast("RDMRecord", self.service.record_cls.pid.resolve(pid_value))
            if current_communities.service.record_cls.pid.resolve(community).id in record.parent.communities:
                continue
            errors = current_rdm_records.record_communities_service.bulk_add(
                self._identity, community, [pid_value], uow=uow
            )
            if errors:
                raise ValueError(f"Can not add record {pid_value} to community {community}: {errors[0]['message']}")

    def _get_oai_record(self, oai_identifier: str) -> OAIHarvestedRecord | None:
        """Get the OAIHarvestedRecord instance by its OAI identifier."""
        return db.session.query(OAIHarvestedRecord).filter_by(oai_identifier=oai_identifier).one_or_none()

    def _check_up_to_date(
        self,
        stream_entry: StreamEntry,
        oai_record: OAIHarvestedRecord | None,
        oai_datestamp: dt.datetime,
        oai_deleted: bool,
        local: LocalRecord,
    ) -> bool:
        """Check if the local record already reflects the harvested one, so writing can be skipped.

        Besides unchanged oai metadata, the local record must be in the harvested state -
        a record deleted or restored locally since the last harvest is written again.
        """
        if not oai_record:
            return False

        if (
            oai_datestamp == oai_record.datestamp
            and oai_deleted == oai_record.deleted
            and not self._update_all
            and oai_record.has_errors is False
            and oai_record.has_warnings is False
        ):
            op_type = local.operation(oai_deleted)
            if oai_deleted:
                # up to date only if the local record is deleted (or absent) as well
                if op_type is Operation.NOOP:
                    stream_entry.entry["record"] = None
                    return True
                return False
            if op_type is not Operation.UPDATE or local.draft is not None:
                # local record is not live (deleted, draft only, missing) or has a local
                # edit draft - write it (the draft gets overwritten and published)
                return False
            # try to read the existing record
            try:
                fetched_record = self.service.read(system_identity, oai_record.record_pid)
                stream_entry.entry["record"] = fetched_record.to_dict()
            except Exception:  # noqa BLE001 ok to catch here
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
        """Read the pid value from the transformed data via the pid provider, if it supports it."""
        pid_field = getattr(self.service.record_cls.pid, "field", None)
        pid_provider = getattr(pid_field, "_provider", None) if pid_field else None
        get_pid_value_from_record = getattr(pid_provider, "get_pid_value_from_record", None) if pid_provider else None
        pid_type = getattr(pid_field, "_pid_type", None) if pid_field else None
        if get_pid_value_from_record and pid_type:
            # try to get pid value from transformed data
            return get_pid_value_from_record(record_data)
        return None

    def _store_oai_record(  # noqa PLR0913,PLR0917
        self,
        oai_record: OAIHarvestedRecord | None,
        oai_identifier: str,
        oai_datestamp: dt.datetime,
        oai_deleted: bool,
        harvested_at: dt.datetime,
        original_data: dict,
        transformed_data: dict | None,
        stream_entry: StreamEntry,
        validation_errors: list[dict],
        exception_raised: Exception | None,
        written_data: dict | None,
    ) -> None:
        """Create or update the OAIHarvestedRecord instance."""
        if not oai_record:
            oai_record = OAIHarvestedRecord(
                oai_identifier=oai_identifier,
                harvester_id=self._harvester_id,
            )
        oai_record.datestamp = oai_datestamp
        oai_record.deleted = oai_deleted
        # store errors and warnings
        # build the list before assigning - in-place append on a JSON column is not persisted
        errors = [self._convert_stream_error(e) for e in (stream_entry.errors or [])]
        errors.extend(validation_errors)
        if exception_raised is not None:
            errors.append(self._convert_exception_to_error_dict(exception_raised))
        if stream_entry.exc:
            errors.append(self._convert_exception_to_error_dict(stream_entry.exc))
        oai_record.errors = json.loads(json.dumps(errors, default=str))
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

        # store the original and transformed data; values that are not json serializable
        # (dates, lazy strings, ...) would make the commit fail
        oai_record.original_data = original_data
        oai_record.transformed_data = json.loads(json.dumps(transformed_data or {}, default=str))

        db.session.add(oai_record)
        db.session.commit()

        current_oai_record_service.indexer.bulk_index([oai_record.oai_identifier])

    def _write(
        self,
        record_data: dict,
        local: LocalRecord,
        op_type: Operation,
        oai_identifier: str,
        uow: UnitOfWork,
    ) -> dict | None:
        """Write the record data using the service.

        Operations other than `NOOP` and `CREATE` always have a pid value - a local
        record without a pid is classified as `ABSENT` (see
        [LocalRecord.resolve][oarepo_oaipmh_harvester.writers.oai_service.LocalRecord.resolve]).
        """
        match op_type:
            case Operation.NOOP:
                return None
            case Operation.CREATE:
                return cast("dict", self.service.create(self._identity, record_data, uow=uow).to_dict())
            case Operation.UPDATE_DRAFT:
                draft_service = cast("DraftRecordService", self.service)
                return cast(
                    "dict",
                    draft_service.update_draft(
                        self._identity, cast("str", local.pid_value), record_data, uow=uow
                    ).to_dict(),
                )
            case Operation.UPDATE | Operation.RESTORE | Operation.REVIVE:
                self._bring_back(local, op_type, uow)
                return self._update(record_data, local, uow)
            case Operation.DELETE | Operation.DELETE_RECORD | Operation.DELETE_DRAFT:
                self._delete(local, op_type, oai_identifier, uow)
                return None
        raise ValueError(f"Unknown operation type: {op_type}")

    def _bring_back(self, local: LocalRecord, op_type: Operation, uow: UnitOfWork) -> None:
        """Make a locally deleted record live again before it is updated (no-op for `UPDATE`)."""
        pid_value = cast("str", local.pid_value)
        if op_type is Operation.RESTORE:
            rdm_service = cast("RDMRecordService", self.service)
            if getattr(local.record, "deletion_status", None) == RecordDeletionStatusEnum.MARKED:
                rdm_service.unmark_record_for_purge(self._identity, pid_value, uow=uow)
            rdm_service.restore_record(self._identity, pid_value, uow=uow)
        elif op_type is Operation.REVIVE:
            self._revive(local)

    def _delete(self, local: LocalRecord, op_type: Operation, oai_identifier: str, uow: UnitOfWork) -> None:
        """Delete the local record (`DELETE` / `DELETE_RECORD`) and its local draft."""
        pid_value = cast("str", local.pid_value)
        if op_type is Operation.DELETE:
            self.service.delete(self._identity, pid_value, uow=uow)
        elif op_type is Operation.DELETE_RECORD:
            cast("RDMRecordService", self.service).delete_record(
                self._identity,
                pid_value,
                {"note": f"Deleted at the OAI-PMH source ({oai_identifier})", "is_visible": True},
                uow=uow,
            )
        self._delete_local_draft(local, uow)

    def _delete_local_draft(self, local: LocalRecord, uow: UnitOfWork) -> None:
        """Delete a local edit draft of a record deleted at the source.

        `delete_record` (now or when the record was tombstoned locally) removes the draft
        from the index but keeps it in the db, while `delete_draft` fails if the draft is
        not indexed - so index it first (the ops run in order on commit).
        """
        if local.draft is not None:
            draft_service = cast("DraftRecordService", self.service)
            uow.register(RecordIndexOp(local.draft, indexer=draft_service.indexer))
            draft_service.delete_draft(self._identity, cast("str", local.pid_value), uow=uow)

    def _revive(self, local: LocalRecord) -> None:
        """Bring a hard deleted record back with its original pid.

        Hard delete sets `model.json` to `None`, but the previous revision still has
        the full json - reverting to it undeletes the record (`is_deleted` is
        `json is None`). The harvested data is applied by the following update.
        """
        record = cast("Record", local.record)
        pid = cast("PersistentIdentifier", local.deleted_pid)
        last_revision_id = next(
            (r.revision_id for r in reversed(record.revisions) if r.model is not None and r.model.json is not None),
            None,
        )
        if last_revision_id is None:
            raise ValueError(f"Hard deleted record {local.pid_value} has no revision to revive from.")
        pid.sync_status(PIDStatus.REGISTERED)
        record.revert(last_revision_id)

    def _update(self, record_data: dict, local: LocalRecord, uow: UnitOfWork) -> dict:
        """Update a live record; draft services do not allow direct update, so go through a draft."""
        pid_value = cast("str", local.pid_value)
        if not self._publish or self._direct_update:
            written = self.service.update(self._identity, pid_value, record_data, uow=uow).to_dict()
            # a local edit draft would otherwise survive (and overwrite the harvested data when published)
            self._delete_local_draft(local, uow)
            return cast("dict", written)
        draft_service = cast("DraftRecordService", self.service)
        # edit returns the existing draft if there is one - it gets overwritten by the harvested data
        draft_service.edit(self._identity, pid_value, uow=uow)
        return cast(
            "dict",
            draft_service.update_draft(self._identity, pid_value, record_data, uow=uow).to_dict(),
        )

    def write_many(self, stream_entries: list[StreamEntry], *args: Any, **kwargs: Any) -> list[StreamEntry]:
        """Write the input entries using a given service."""
        # For now, just call write() for each entry
        return [self.write(stream_entry, *args, **kwargs) for stream_entry in stream_entries]

    def _convert_exception_to_error_dict(self, exception: Exception) -> dict:
        """Turn an exception into an error dict with a trimmed traceback and its locals."""
        tb = exception.__traceback__
        formatted_tb = []
        while tb:
            frame = tb.tb_frame
            fn = (frame.f_code.co_filename or "").split("site-packages/")[-1]
            formatted_tb.append(f"{frame.f_code.co_name}@{fn}:{tb.tb_lineno}")
            for local_name, local_value in frame.f_locals.items():
                try:
                    local_value_str = repr(local_value)
                except Exception:  # noqa: BLE001 a broken repr must not prevent storing the error
                    local_value_str = f"<{type(local_value).__name__}, repr failed>"
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
        """Normalize a stream error (dict, exception or other) into an error dict."""
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
