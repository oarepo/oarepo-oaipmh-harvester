# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""E-mail report sent to the harvest managers when a harvest ends.

[harvest_oaipmh_records][oarepo_oaipmh_harvester.tasks.harvest_oaipmh_records] collects
the outcome of every record in a [HarvestReport][oarepo_oaipmh_harvester.report.HarvestReport]
and calls [send_harvest_report][oarepo_oaipmh_harvester.report.send_harvest_report] at the
end - also when the harvest itself fails (e.g. the source is unreachable).

The mail is rendered from the `oarepo_oaipmh_harvester/harvest_report.jinja` template,
with the blocks `subject`, `html_body` and `plain_body` as in invenio notifications. The
template comes from this package's templates blueprint
([create_templates_blueprint][oarepo_oaipmh_harvester.report.create_templates_blueprint]);
the application's own templates take precedence, so an instance can override it by
placing its own copy into its `templates/oarepo_oaipmh_harvester/` folder. It gets
`harvester` and `report` in its context and can use `_()` and `invenio_url_for()`.

The mail is sent (via the `invenio_mail` celery task) only if the harvester has harvest
managers; it goes to their e-mail addresses.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from flask import Blueprint, Flask, current_app
from invenio_accounts.models import User
from invenio_mail.tasks import send_email

if TYPE_CHECKING:
    from oarepo_oaipmh_harvester.oai_harvester.api import OAIHarvesterAggregate

MAX_REPORTED_FAILURES = 100
"""At most this many failed records are listed in the mail."""

TEMPLATE = "oarepo_oaipmh_harvester/harvest_report.jinja"


@dataclass
class HarvestReport:
    """Outcome of a harvest."""

    started_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    finished_at: dt.datetime | None = None
    ok: int = 0
    failed: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)
    """`(oai identifier, error summary)` of the first `MAX_REPORTED_FAILURES` failed records."""
    error: str | None = None
    """Error that stopped the whole harvest, if any."""

    def add_ok(self) -> None:
        """Count a successfully processed record."""
        self.ok += 1

    def add_failure(self, oai_identifier: str, summary: str) -> None:
        """Count a failed record, keep it for the listing if there is still room."""
        self.failed += 1
        if len(self.failures) < MAX_REPORTED_FAILURES:
            self.failures.append((oai_identifier, summary))


def send_harvest_report(harvester: OAIHarvesterAggregate, report: HarvestReport) -> None:
    """Send the report to the harvest managers of the harvester (if it has any)."""
    user_ids = [manager["user"] for manager in harvester.harvest_managers or []]
    recipients = [user.email for user in User.query.filter(User.id.in_(user_ids)) if user.email] if user_ids else []
    if not recipients:
        return
    content = _render_blocks(TEMPLATE, harvester=harvester, report=report)
    send_email.delay(
        {
            "subject": content["subject"].strip(),
            "html": content["html_body"],
            "body": content["plain_body"],
            "recipients": recipients,
            "sender": current_app.config["MAIL_DEFAULT_SENDER"],
        }
    )


def _render_blocks(template_name: str, **context: Any) -> dict[str, str]:
    """Render all blocks of the template, as invenio notifications do."""
    template = current_app.jinja_env.get_template(template_name)
    ctx = template.new_context(context)
    # render the whole template first so that its top-level `set` variables exist for the blocks
    list(template.root_render_func(ctx))
    return {name: "".join(block(ctx)) for name, block in template.blocks.items()}


def create_templates_blueprint(_app: Flask) -> Blueprint:
    """Blueprint making the package's templates available (registered in both UI and API apps)."""
    return Blueprint("oarepo_oaipmh_harvester_templates", __name__, template_folder="templates")
