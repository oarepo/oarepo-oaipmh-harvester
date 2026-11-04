# SPDX-FileCopyrightText: 2024-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Building the datastream of a harvest and running it.

The datastream is built from the harvester definition (see
[create_datastream][oarepo_oaipmh_harvester.datastream.create_datastream]):

* reader - the harvester's `loader` (default `oai-pmh`, the invenio-vocabularies OAI-PMH
  reader), with `base_url`, `metadata_prefix`, `set`, `identifiers` filled in unless given in
  the loader options, and the `from_date` / `until_date` range of the harvest (from `since` /
  `until`, formatted to the granularity of the source, see
  [format_oaipmh_datestamp][oarepo_oaipmh_harvester.oai_source.format_oaipmh_datestamp]);
* transformers and writers - the harvester's `transformers` / `writers`.

Each definition is a string `name{options}` where options are a JSON5 object
([parse_config][oarepo_oaipmh_harvester.pipeline.parse_config]); `harvester_id` is always
added to the options. The names are looked up in `VOCABULARIES_DATASTREAM_READERS` /
`_TRANSFORMERS` / `_WRITERS`.

[run_harvest][oarepo_oaipmh_harvester.pipeline.run_harvest] runs the datastream and records
the outcome of every record in a
[HarvestReport][oarepo_oaipmh_harvester.report.HarvestReport]; a failure of a single record
is stored on its harvest record and the harvest continues.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, cast

import json5
from flask import current_app
from invenio_vocabularies.datastreams.errors import ReaderError

from oarepo_oaipmh_harvester.datastream import create_datastream
from oarepo_oaipmh_harvester.oai_source import OAIPMHSource, format_oaipmh_datestamp
from oarepo_oaipmh_harvester.writers.oai_service import Operation

if TYPE_CHECKING:
    from invenio_vocabularies.datastreams.datastreams import DataStream

    from oarepo_oaipmh_harvester.oai_harvester.api import OAIHarvesterAggregate
    from oarepo_oaipmh_harvester.report import HarvestReport

MAX_LOGGED_ERROR_LENGTH = 300


def parse_config(config: str) -> tuple[str, dict]:
    """Parse a config string of the form type{args}."""
    # the config is a single line, like xml{props}
    # props are json5 style key-value pairs
    # the result is {"type": "oai-import", "args": {"model": "test"}}
    if "{" not in config:
        return config, {}
    type_, args_str = config.split("{", 1)
    args_str = "{" + args_str

    args = cast("dict", json5.loads(args_str))
    return type_, args


def create_readers(
    harvester: OAIHarvesterAggregate,
    since: datetime | str | None = None,
    oai_ids: list[str] | None = None,
    until: datetime | str | None = None,
) -> dict:
    """Create readers config for the harvester."""
    reader_type, reader_args = parse_config(harvester.loader or "oai-pmh")
    if "base_url" not in reader_args:
        reader_args["base_url"] = harvester.base_url
    if "metadata_prefix" not in reader_args and harvester.metadata_prefix:
        reader_args["metadata_prefix"] = harvester.metadata_prefix
    if "set" not in reader_args and harvester.setspec:
        reader_args["set"] = harvester.setspec
    if "from_date" not in reader_args and since:
        if isinstance(since, datetime | str):
            since = format_oaipmh_datestamp(since, reader_args["base_url"])
        reader_args["from_date"] = since
    if "until_date" not in reader_args and until:
        if isinstance(until, datetime | str):
            until = format_oaipmh_datestamp(until, reader_args["base_url"])
        reader_args["until_date"] = until
    if oai_ids is not None:
        reader_args["identifiers"] = oai_ids
    reader_args["harvester_id"] = harvester.id
    return {
        "type": reader_type,
        "args": reader_args,
    }


def create_transformers(harvester: OAIHarvesterAggregate) -> list[dict]:
    """Create transformers config for the harvester."""
    transformers = []
    for transformer_config in harvester.transformers or []:
        transformer_type, transformer_args = parse_config(transformer_config)
        transformer_args["harvester_id"] = harvester.id
        transformers.append(
            {
                "type": transformer_type,
                "args": transformer_args,
            }
        )
    return transformers


def create_writers(harvester: OAIHarvesterAggregate, overrides: dict | None = None) -> list[dict]:
    """Create writers config for the harvester, merging `overrides` into the `oai-service` ones."""
    writers = []
    for writer_config in harvester.writers or []:
        writer_type, writer_args = parse_config(writer_config)
        writer_args["harvester_id"] = harvester.id
        if overrides and writer_type == "oai-service":
            writer_args.update(overrides)
        writers.append(
            {
                "type": writer_type,
                "args": writer_args,
            }
        )
    return writers


def no_records(readers_config: dict) -> bool:
    """Whether an OAI-PMH reader has nothing to read for its range.

    Selected identifiers are not probed - they are a list of records, not a range. A source
    that can not be probed is given the benefit of doubt; the harvest itself reports its
    errors.
    """
    if readers_config["type"] != "oai-pmh":
        return False
    reader_args = readers_config["args"]
    if "identifiers" in reader_args:
        return False
    try:
        source = OAIPMHSource(
            reader_args["base_url"],
            metadata_prefix=reader_args.get("metadata_prefix"),
            set_=reader_args.get("set"),
        )
        # the range is already formatted for the source (see create_readers), so this is one
        # request and no Identify
        return source.count(reader_args.get("from_date"), reader_args.get("until_date")) == 0
    except Exception:
        current_app.logger.warning("Could not check what the range holds, harvesting it", exc_info=True)
        return False


def run_harvest(  # noqa: PLR0913 mirrors the task arguments
    harvester: OAIHarvesterAggregate,
    report: HarvestReport,
    *,
    oai_ids: list[str] | None,
    since: datetime | None,
    until: datetime | None,
    batch_size: int | None,
    writer_overrides: dict | None = None,
    probe: bool = True,
) -> None:
    """Run the harvest, recording the outcome of every record in the report.

    With `probe`, a range with no records is left alone - the reader reports the empty listing
    as a generic `ReaderError`, which would otherwise fail the whole harvest. The window tasks
    of a parallel harvest skip the probe when the planner has already counted the window; a
    window that lost its records in the meantime (they were modified at the source, so they
    moved to a later window) is then recognised as empty by the error and counted once.
    """
    readers_config = create_readers(harvester, since=since, oai_ids=oai_ids, until=until)
    if probe and no_records(readers_config):
        current_app.logger.info("No records to harvest for %s", harvester.id)
        return
    transformers_config = create_transformers(harvester)
    writers_config = create_writers(harvester, writer_overrides)
    datastream = create_datastream(
        readers_config=[readers_config],
        transformers_config=transformers_config,
        writers_config=writers_config,
        batch_size=batch_size or current_app.config["OAI_HARVESTER_DEFAULT_BATCH_SIZE"],
    )
    try:
        _process(datastream, report)
    except ReaderError:
        # a generic reader error - only when the range was not probed can it mean "empty"
        if probe or not no_records(readers_config):
            raise
        current_app.logger.info("No records left to harvest for %s", harvester.id)


def _process(datastream: DataStream, report: HarvestReport) -> None:
    """Iterate the datastream, recording the outcome of every entry in the report."""
    for _entry in datastream.process():
        oai_record = _entry.entry.get("oai_record") if isinstance(_entry.entry, dict) else None
        oai_identifier = oai_record.header.identifier if oai_record is not None else "<unknown>"
        if _entry.errors or _entry.exc:
            problems = [
                *map(str, _entry.errors),
                *([f"{type(_entry.exc).__name__}: {_entry.exc}"] if _entry.exc else []),
            ]
            summary = " ".join("; ".join(problems).split())
            if len(summary) > MAX_LOGGED_ERROR_LENGTH:
                summary = summary[: MAX_LOGGED_ERROR_LENGTH - 3] + "..."
            current_app.logger.error("Entry %s: failed: %s", oai_identifier, summary)
            report.add_failure(oai_identifier, summary)
        elif _entry.filtered:
            current_app.logger.info("Entry %s: skipped", oai_identifier)
            report.add_ok()
        else:
            current_app.logger.info("Entry %s: processed successfully", oai_identifier)
            report.add_ok()
            if _entry.op_type == Operation.CREATE:
                report.created += 1
            elif _entry.op_type in (Operation.UPDATE, Operation.UPDATE_DRAFT, Operation.RESTORE, Operation.REVIVE):
                report.updated += 1
