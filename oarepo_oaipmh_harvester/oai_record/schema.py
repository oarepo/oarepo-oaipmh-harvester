# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Schema for OAI-PMH harvested records."""

from __future__ import annotations

from invenio_records_resources.services.records.schema import (
    BaseRecordSchema,
)
from marshmallow import fields


class OAIHarvestedRecordSchema(BaseRecordSchema):
    """Schema for OAI-PMH harvested records."""

    oai_identifier = fields.String(required=True)
    """The OAI identifier of the record."""
    record_pid = fields.String(allow_none=True)
    """The persistent identifier of the record."""
    datestamp = fields.DateTime(required=True)
    """The datestamp of the record."""
    harvested_at = fields.DateTime(required=True)
    """The time when the record was harvested."""
    deleted = fields.Boolean(default=False, required=True)
    """True if the record was deleted during the harvest."""
    has_errors = fields.Boolean(default=False, required=True)
    """True if the record has errors during the harvest."""
    has_warnings = fields.Boolean(default=False, required=True)
    """True if the record has warnings during the harvest."""
    errors = fields.List(fields.Dict(default=dict, load_default=dict))
    """Errors."""
    original_data = fields.Dict(default=dict, load_default=dict)
    """Original data."""
    transformed_data = fields.Dict(default=dict, load_default=dict)
    """Transformed data."""
    run_id = fields.String(required=True)
    """The run ID of the record."""

    class Meta:
        """Meta class for OAIHarvestedRecordSchema."""

        strict = True
