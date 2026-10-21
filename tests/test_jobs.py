# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

from __future__ import annotations

import pytest
from invenio_db import db
from sqlalchemy import event
from sqlalchemy.pool import QueuePool

from oarepo_oaipmh_harvester.jobs import register_current_harvesters


@pytest.fixture(scope="module")
def app_config(app_config):
    # pytest-invenio uses NullPool, which never keeps connections; use a real
    # pool as in production so that a leaked pooled connection is detectable
    app_config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        **app_config.get("SQLALCHEMY_ENGINE_OPTIONS", {}),
        "poolclass": QueuePool,
    }
    return app_config


def test_register_current_harvesters_leaves_no_pooled_connection(app, database):
    """Processes forked after app creation must not inherit an open DB connection."""
    database.engine.dispose()
    pool = database.engine.pool

    # an invalidated connection stays in the pool as an empty record, so count
    # the open DBAPI connections instead of the checked-in records
    open_connections = set()

    def on_connect(dbapi_connection, connection_record):
        open_connections.add(id(dbapi_connection))

    def on_close(dbapi_connection, connection_record):
        open_connections.discard(id(dbapi_connection))

    event.listen(pool, "connect", on_connect)
    event.listen(pool, "close", on_close)
    try:
        register_current_harvesters()
        db.session.remove()
    finally:
        event.remove(pool, "connect", on_connect)
        event.remove(pool, "close", on_close)

    assert not open_connections
