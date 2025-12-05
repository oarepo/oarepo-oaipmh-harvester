# noqa N999
#
# This file is part of Invenio.
# Copyright (C) 2025 CESNET z.s.p.o.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Create oarepo-oaipmh-harvester branch."""

from __future__ import annotations

# revision identifiers, used by Alembic.

revision = "1764502279"
down_revision = None
branch_labels = ("oarepo_oaipmh_harvester",)
depends_on = None


def upgrade() -> None:
    """Upgrade database."""


def downgrade() -> None:
    """Downgrade database."""
