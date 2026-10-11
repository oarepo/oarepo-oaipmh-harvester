# noqa N999
#
# This file is part of Invenio.
# Copyright (C) 2026 CESNET z.s.p.o.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Store oai harvest record datestamp and harvested_at as timezone aware (UTC) timestamps."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "1791708839"
down_revision = "1764935017"
branch_labels = ()
depends_on = None

COLUMNS = ("datestamp", "harvested_at")


def upgrade() -> None:
    """Upgrade database."""
    for column in COLUMNS:
        # existing naive values are UTC
        op.alter_column(
            "oai_harvest_records",
            column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=False,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    """Downgrade database."""
    for column in COLUMNS:
        op.alter_column(
            "oai_harvest_records",
            column,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
