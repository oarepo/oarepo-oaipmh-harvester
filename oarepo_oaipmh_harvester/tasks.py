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

from typing import TYPE_CHECKING, cast

import json5
from celery.app import shared_task
from flask import current_app
from invenio_vocabularies.datastreams.factories import DataStreamFactory

from oarepo_oaipmh_harvester.oai_harvester.api import OAIHarvesterAggregate

if TYPE_CHECKING:
    from datetime import datetime


@shared_task
def harvest_oaipmh_records(*, harvester_id: str, since: datetime | None = None, batch_size: int = 10) -> None:
    """Harvest OAI-PMH records for the given harvester."""
    harvester = OAIHarvesterAggregate.get_record(harvester_id)
    readers_config = create_readers(harvester, since=since)
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


def create_readers(harvester: OAIHarvesterAggregate, since: datetime | None = None) -> dict:
    """Create readers config for the harvester."""
    reader_type, reader_args = parse_config(harvester.loader or "oai-pmh")
    if "base_url" not in reader_args:
        reader_args["base_url"] = harvester.base_url
    if "metadata_prefix" not in reader_args and harvester.metadata_prefix:
        reader_args["metadata_prefix"] = harvester.metadata_prefix
    if "set" not in reader_args and harvester.setspec:
        reader_args["set"] = harvester.setspec
    if "from_date" not in reader_args and since:
        reader_args["from_date"] = since.isoformat()
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
