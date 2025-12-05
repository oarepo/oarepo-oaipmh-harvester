#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Schema for OAI Harvester."""

from __future__ import annotations

import marshmallow as ma
from invenio_records_resources.services.records.schema import (
    BaseRecordSchema,
)
from marshmallow import fields


class HarvestManagerSchema(ma.Schema):
    """Schema for a harvest manager."""

    user = fields.String(required=True)
    """The user ID of the harvest manager."""

    class Meta:
        """Meta class for HarvestManagerSchema."""

        strict = True


class OAIHarvesterSchema(BaseRecordSchema):
    """Schema for OAI Harvester."""

    id = fields.String(required=True)
    """The ID of the OAI harvester."""

    base_url = fields.String(required=True)
    """The base URL of the OAI-PMH service."""

    name = fields.String(required=True)
    """The name of the harvester."""

    comment = fields.String()
    """Comment."""

    metadata_prefix = fields.String(required=True)
    """The metadata prefix to harvest."""

    setspec = fields.String()
    """The set specifications to harvest."""

    loader = fields.String(required=True)
    """The definition of the loader."""

    transformers = fields.List(fields.String(), load_default=list)
    """The list of transformers."""

    writers = fields.List(fields.String(), load_default=list)
    """The list of writers."""

    harvest_managers = fields.List(fields.Nested(HarvestManagerSchema), load_default=list)
    """The list of writers."""

    class Meta:
        """Meta class for OAIHarvesterSchema."""

        strict = True
