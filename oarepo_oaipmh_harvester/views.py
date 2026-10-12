# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""UI views - the public `/about/harvest` page listing the harvesters.

The page is rendered from `oarepo_oaipmh_harvester/about_harvest.html` (override it in the
instance's `templates/oarepo_oaipmh_harvester/` folder). It gets `harvesters` - a list of
`(harvester, stats, can_manage)` ordered by the harvester name, `stats` having
`last_harvested`, `records` and `failed` (records whose last harvest has errors), and
`can_manage` telling whether the current user may open the harvester in the administration
(administration access or harvest manager of the harvester) - links are shown then.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Flask, render_template
from invenio_access.permissions import Permission
from invenio_administration.permissions import administration_access_action
from invenio_db import db
from sqlalchemy import func

from oarepo_oaipmh_harvester.oai_harvester.models import OAIHarvester
from oarepo_oaipmh_harvester.oai_record.models import OAIHarvestedRecord
from oarepo_oaipmh_harvester.permissions import harvest_manager_need


def about_harvest() -> str:
    """Render the list of harvesters with their configuration and statistics."""
    record = OAIHarvestedRecord
    stats = {
        harvester_id: {"last_harvested": last_harvested, "records": records, "failed": failed}
        for harvester_id, last_harvested, records, failed in db.session.query(
            record.harvester_id,
            func.max(record.harvested_at),
            func.count(),
            func.count().filter(record.has_errors.is_(True)),
        ).group_by(record.harvester_id)
    }
    empty: dict[str, Any] = {"last_harvested": None, "records": 0, "failed": 0}
    harvesters = [(h, stats.get(h.id, empty), _can_manage(h)) for h in OAIHarvester.query.order_by(OAIHarvester.name)]
    return render_template("oarepo_oaipmh_harvester/about_harvest.html", harvesters=harvesters)


def _can_manage(harvester: OAIHarvester) -> bool:
    """Return whether the current user has administration access or manages the harvester."""
    managers = [harvest_manager_need(m) for m in harvester.harvest_managers or [] if "user" in m]
    return Permission(administration_access_action, *managers).can()


def create_ui_blueprint(_app: Flask) -> Blueprint:
    """UI blueprint with the `/about/harvest` page and the package's templates."""
    blueprint = Blueprint("oarepo_oaipmh_harvester_ui", __name__, template_folder="templates")
    blueprint.add_url_rule("/about/harvest", view_func=about_harvest)
    return blueprint
