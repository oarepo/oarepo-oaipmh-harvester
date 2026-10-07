#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Tasks for OAI-PMH Harvester."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import cast

import json5
from celery.app import shared_task
from flask import current_app
from invenio_jobs.jobs import JobType
from invenio_vocabularies.datastreams.factories import DataStreamFactory

from oarepo_oaipmh_harvester.oai_harvester.api import OAIHarvesterAggregate
from oarepo_oaipmh_harvester.oai_harvester.models import OAIHarvester

_SECONDS_GRANULARITY = "YYYY-MM-DDThh:mm:ssZ"


@lru_cache(maxsize=32)
def _oai_granularity(base_url: str) -> str | None:
    """Return the granularity advertised by the OAI-PMH Identify verb (cached).

    Returns None if the probe fails - callers should fall back to the most
    restrictive date-only format, which is legal under both granularities.
    Note: results are cached for the process lifetime, so a granularity change
    on the server side requires a worker restart to take effect.
    """
    try:
        from oaipmh_scythe import Scythe

        return getattr(Scythe(base_url).identify(), "granularity", None)
    except Exception:
        current_app.logger.warning(
            "Could not probe Identify granularity of %s, assuming date-only", base_url, exc_info=True
        )
        return None


def format_oaipmh_datestamp(since: datetime | str, base_url: str) -> str:
    """Format `since` as an OAI-PMH datestamp matching the server granularity.

    OAI-PMH repositories that advertise ``YYYY-MM-DD`` granularity (e.g. the
    ASEP ARL server) reject any time component, while ``...+00:00`` offsets
    produced by ``datetime.isoformat()`` are illegal in both granularities.
    Seconds-granularity servers get ``YYYY-MM-DDThh:mm:ssZ`` (UTC), others a
    bare ``YYYY-MM-DD``.
    """
    if isinstance(since, str):
        import arrow

        since_dt = arrow.get(since).datetime
    else:
        since_dt = since

    if since_dt.utcoffset() is None:
        since_dt = since_dt.astimezone()  # interpret naive input as local time
    since_dt = since_dt.astimezone(UTC)
    if _oai_granularity(base_url) == _SECONDS_GRANULARITY:
        return cast("str", since_dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return cast("str", since_dt.date().isoformat())


@shared_task
def harvest_oaipmh_records(
    *,
    harvester_id: str,
    oai_ids: list[str] | None = None,
    since: datetime | None = None,
    batch_size: int | None = None,
) -> None:
    """Harvest OAI-PMH records for the given harvester."""
    harvester = OAIHarvesterAggregate.get_record(harvester_id)
    readers_config = create_readers(harvester, since=since, oai_ids=oai_ids)
    transformers_config = create_transformers(harvester)
    writers_config = create_writers(harvester)
    datastream = DataStreamFactory.create(
        readers_config=[readers_config],
        transformers_config=transformers_config,
        writers_config=writers_config,
        batch_size=batch_size or current_app.config["OAI_HARVESTER_DEFAULT_BATCH_SIZE"],
    )
    for _entry in datastream.process():
        oai_identifier = _entry.entry["oai_record"].header.identifier
        if _entry.errors:
            current_app.logger.error("Entry %s: errors: %s", oai_identifier, _entry.errors)
        else:
            current_app.logger.info("Entry %s: processed successfully", oai_identifier)


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


def create_writers(harvester: OAIHarvesterAggregate) -> list[dict]:
    """Create writers config for the harvester."""
    writers = []
    for writer_config in harvester.writers or []:
        writer_type, writer_args = parse_config(writer_config)
        writer_args["harvester_id"] = harvester.id
        writers.append(
            {
                "type": writer_type,
                "args": writer_args,
            }
        )
    return writers


@shared_task(ignore_result=True)
def run_all_harvesters() -> None:
    """Run all OAI-PMH harvester tasks."""
    harvesters = OAIHarvester.query.all()
    for harvester in harvesters:
        try:
            current_app.logger.info("Started harvesting %s", harvester.id)
            harvest_oaipmh_records(harvester_id=harvester.id)
            current_app.logger.info("Successfully harvested %s", harvester.id)
        except Exception:  # pragma: no cover
            current_app.logger.exception("Exception during harvesting %s", harvester.id)


class RunAllHarvesters(JobType):
    """A job type to run invenio CLI commands as Celery tasks."""

    id = "run_all_harvesters"
    title = "Run all harvester tasks"
    description = "Run all harvester tasks."
    task = run_all_harvesters
