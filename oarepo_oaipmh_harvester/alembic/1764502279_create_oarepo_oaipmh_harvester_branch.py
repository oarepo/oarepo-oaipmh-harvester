# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

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
