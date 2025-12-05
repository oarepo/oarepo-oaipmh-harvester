# noqa N999
#
# This file is part of Invenio.
# Copyright (C) 2016-2018 CERN.
#
# Invenio is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""OAI harvester tables."""

from __future__ import annotations

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op
from sqlalchemy.dialects import mysql, postgresql

# revision identifiers, used by Alembic.
revision = "1764935017"
down_revision = "1764502279"
branch_labels = ()
depends_on = None


def upgrade() -> None:
    """Upgrade database."""
    op.create_table(
        "oai_harvesters",
        sa.Column("id", sa.String(length=30), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("metadata_prefix", sa.String(length=64), nullable=False),
        sa.Column("setspec", sa.String(length=255), nullable=True),
        sa.Column("loader", sa.String(length=255), nullable=False),
        sa.Column("transformers", sqlalchemy_utils.types.json.JSONType(), nullable=False),
        sa.Column("writers", sqlalchemy_utils.types.json.JSONType(), nullable=False),
        sa.Column("harvest_managers", sqlalchemy_utils.types.json.JSONType(), nullable=False),
        sa.Column(
            "created",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "updated",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oai_harvesters")),
    )
    op.create_table(
        "oai_harvest_records",
        sa.Column("oai_identifier", sa.String(length=255), nullable=False),
        sa.Column("record_type", sa.String(length=32), nullable=True),
        sa.Column("record_pid", sa.String(length=255), nullable=True),
        sa.Column("datestamp", sa.DateTime(), nullable=False),
        sa.Column("harvested_at", sa.DateTime(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("has_errors", sa.Boolean(), nullable=False),
        sa.Column("has_warnings", sa.Boolean(), nullable=False),
        sa.Column(
            "errors",
            sa.JSON()
            .with_variant(sqlalchemy_utils.types.json.JSONType(), "mysql")
            .with_variant(postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql")
            .with_variant(sqlalchemy_utils.types.json.JSONType(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "original_data",
            sa.JSON()
            .with_variant(sqlalchemy_utils.types.json.JSONType(), "mysql")
            .with_variant(postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql")
            .with_variant(sqlalchemy_utils.types.json.JSONType(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "transformed_data",
            sa.JSON()
            .with_variant(sqlalchemy_utils.types.json.JSONType(), "mysql")
            .with_variant(postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql")
            .with_variant(sqlalchemy_utils.types.json.JSONType(), "sqlite"),
            nullable=False,
        ),
        sa.Column("harvester_id", sa.String(length=30), nullable=False),
        sa.Column(
            "job_run_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["harvester_id"],
            ["oai_harvesters.id"],
            name=op.f("fk_oai_harvest_records_harvester_id_oai_harvesters"),
        ),
        sa.PrimaryKeyConstraint("oai_identifier", name=op.f("pk_oai_harvest_records")),
    )


def downgrade() -> None:
    """Downgrade database."""
    op.drop_table("oai_harvest_records")
    op.drop_table("oai_harvesters")
