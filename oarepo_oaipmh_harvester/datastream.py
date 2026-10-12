# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Harvest datastream that never stops because of a single record.

The invenio-vocabularies `DataStream` catches only `TransformerError` / `WriterError` -
any other exception raised for a record (e.g. a marshmallow `ValidationError` from an
import deserializer) stops the whole harvest. Entries with transformation errors are not
passed to the writers either, so the failure would never get to the harvest record.

[create_datastream][oarepo_oaipmh_harvester.datastream.create_datastream] therefore wraps

* each transformer in [CatchingTransformer][oarepo_oaipmh_harvester.datastream.CatchingTransformer] -
  any exception (and errors a transformer reports in `errors` without raising, as a
  `TransformerError`) is stored on the entry as `exc` (not in `errors`, so the datastream
  still hands the entry to the writers), the entry's data is replaced with
  `{"record": None, "oai_record": <OAI record>}` and the following transformers pass it
  through. The `oai-service` writer stores the exception on the harvest record and leaves
  the local record as it is;
* each writer in [CatchingWriter][oarepo_oaipmh_harvester.datastream.CatchingWriter] -
  any exception is stored on the entry as `exc`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override

from flask import current_app
from invenio_db import db
from invenio_vocabularies.datastreams.datastreams import DataStream
from invenio_vocabularies.datastreams.errors import TransformerError
from invenio_vocabularies.datastreams.factories import (
    ReaderFactory,
    TransformerFactory,
    WriterFactory,
)
from invenio_vocabularies.datastreams.transformers import BaseTransformer
from invenio_vocabularies.datastreams.writers import BaseWriter

if TYPE_CHECKING:
    from invenio_vocabularies.datastreams.datastreams import StreamEntry


def _is_oai_record(value: Any) -> bool:
    """Return whether the value looks like an OAI record (has `header.identifier`)."""
    return getattr(getattr(value, "header", None), "identifier", None) is not None


def _oai_record(entry: Any) -> Any:
    """Return the OAI record of an entry, or `None`.

    Readers yield either the record itself or `{"record": <record>}` (the invenio OAI-PMH
    reader); transformed entries keep it in `oai_record`.
    """
    if _is_oai_record(entry):
        return entry
    if isinstance(entry, dict):
        for key in ("oai_record", "record"):
            if _is_oai_record(entry.get(key)):
                return entry[key]
    return None


class CatchingTransformer(BaseTransformer):
    """Store any exception of the wrapped transformer on the entry instead of raising it."""

    def __init__(self, transformer: BaseTransformer) -> None:
        """Wrap the transformer."""
        self._transformer = transformer

    @override
    def apply(self, stream_entry: StreamEntry, *args: Any, **kwargs: Any) -> StreamEntry:
        """Apply the wrapped transformer, unless a previous one has failed."""
        if stream_entry.exc is not None:
            return stream_entry
        oai_record = _oai_record(stream_entry.entry)
        try:
            result = self._transformer.apply(stream_entry, *args, **kwargs)
        except Exception as err:  # a single record must not stop the harvest
            current_app.logger.exception(
                "Error transforming %s", oai_record.header.identifier if oai_record else stream_entry.entry
            )
            return _failed(stream_entry, oai_record, err)
        if result.errors:
            # errors reported without raising - the datastream would not hand the entry to
            # the writers, so turn them into an exception that is stored on the harvest record
            message = "; ".join(str(error) for error in result.errors)
            return _failed(result, oai_record, TransformerError(f"{type(self._transformer).__name__}: {message}"))
        return result


def _failed(stream_entry: StreamEntry, oai_record: Any, exc: Exception) -> StreamEntry:
    """Mark the entry as failed with the exception; it is still passed to the writers."""
    stream_entry.exc = exc
    stream_entry.errors = []
    stream_entry.entry = {"record": None, "oai_record": oai_record}
    return stream_entry


class CatchingWriter(BaseWriter):
    """Store any exception of the wrapped writer on the entry instead of raising it."""

    def __init__(self, writer: BaseWriter) -> None:
        """Wrap the writer."""
        super().__init__()
        self._writer = writer
        self.is_async = getattr(writer, "is_async", False)

    @override
    def write(self, stream_entry: StreamEntry, *args: Any, **kwargs: Any) -> StreamEntry:
        """Write the entry with the wrapped writer."""
        try:
            return self._writer.write(stream_entry, *args, **kwargs)
        except Exception as err:  # a single record must not stop the harvest
            current_app.logger.exception("Error writing %s", stream_entry.entry)
            # we can't know the state of the db connection, rollback is a safe bet
            db.session.rollback()
            stream_entry.exc = err
            return stream_entry

    @override
    def write_many(self, stream_entries: list[StreamEntry], *args: Any, **kwargs: Any) -> list[StreamEntry]:
        """Write the entries one by one, so that a failure affects only its entry."""
        return [self.write(stream_entry, *args, **kwargs) for stream_entry in stream_entries]


def create_datastream(
    readers_config: list[dict],
    transformers_config: list[dict],
    writers_config: list[dict],
    **kwargs: Any,
) -> DataStream:
    """Create a datastream (as `DataStreamFactory.create`) with error catching transformers and writers."""
    return DataStream(
        readers=[ReaderFactory.create(config) for config in readers_config],
        transformers=[CatchingTransformer(TransformerFactory.create(config)) for config in transformers_config],
        writers=[CatchingWriter(WriterFactory.create(config)) for config in writers_config],
        **kwargs,
    )
