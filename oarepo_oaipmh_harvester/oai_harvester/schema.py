# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Schema for OAI Harvester."""

from __future__ import annotations

from typing import Any

import marshmallow as ma
from invenio_accounts.models import User
from invenio_records_resources.services.records.schema import (
    BaseRecordSchema,
)
from marshmallow import fields


class HarvestManagerSchema(ma.Schema):
    """Schema for a harvest manager."""

    user = fields.String(required=True)
    """The user ID of the harvest manager."""

    @ma.pre_load
    def _load_email(self, data: Any, **_kwargs: Any) -> Any:
        """Accept an e-mail address (administration form) instead of `{"user": <id>}`."""
        if not isinstance(data, str):
            return data
        user = User.query.filter_by(email=data).one_or_none()
        if user is None:
            raise ma.ValidationError(f"No user with e-mail {data}.")
        return {"user": str(user.id)}


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
    """The list of harvest managers."""

    @ma.pre_load
    def _load_form_text(self, data: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        """Accept the administration form's textareas - newline separated values.

        Lists (the REST API) pass through unchanged; e-mail addresses of harvest managers
        are converted by [HarvestManagerSchema][oarepo_oaipmh_harvester.oai_harvester.schema.HarvestManagerSchema].
        """
        data = dict(data)
        for key in ("transformers", "writers", "harvest_managers"):
            if isinstance(data.get(key), str):
                data[key] = [line.strip() for line in data[key].splitlines() if line.strip()]
        return data


class HarvestActionSchema(ma.Schema):
    """Payload of the administration "Run" action."""

    all_records = fields.Boolean(
        load_default=False,
        metadata={
            "title": "Harvest all records",
            "description": "If not checked, only records modified since the last harvest are harvested.",
        },
    )
