# SPDX-FileCopyrightText: 2024-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Harvest Celery tasks and job types.

[harvest_oaipmh_records][oarepo_oaipmh_harvester.tasks.harvest_oaipmh_records] is the task
behind every harvester's job. It either harvests the records right away - the datastream is
built from the harvester definition and run by
[run_harvest][oarepo_oaipmh_harvester.pipeline.run_harvest], see
[pipeline][oarepo_oaipmh_harvester.pipeline] - or, with `parallel=True`, splits the work into
time windows harvested at the same time as subtask runs of the job run, see
[parallel][oarepo_oaipmh_harvester.parallel]. A parallel harvest needs a job run with the
`parallel` argument set (`invenio oai harvest <id> --parallel` or the run form in
*Administration -> Jobs*), harvests everything and is only started for the `oai-pmh` loader;
anything else falls back to the sequential harvest with a warning.

[run_all_harvesters][oarepo_oaipmh_harvester.tasks.run_all_harvesters] (job type
[RunAllHarvesters][oarepo_oaipmh_harvester.tasks.RunAllHarvesters]) runs a full harvest of all
harvesters.

The datastream helpers ([create_readers][oarepo_oaipmh_harvester.pipeline.create_readers] and
the rest of [pipeline][oarepo_oaipmh_harvester.pipeline]) used to live in this module and stay
importable from it; `harvest_window` is imported so that celery registers the window task when
`invenio_celery.tasks` imports this module.
"""

from __future__ import annotations

from datetime import UTC, datetime

from celery.app import shared_task
from flask import current_app
from invenio_jobs.jobs import JobType

from oarepo_oaipmh_harvester.oai_harvester.api import OAIHarvesterAggregate
from oarepo_oaipmh_harvester.oai_harvester.models import OAIHarvester
from oarepo_oaipmh_harvester.oai_source import format_oaipmh_datestamp
from oarepo_oaipmh_harvester.parallel import harvest_window, start_parallel_harvest
from oarepo_oaipmh_harvester.pipeline import (
    create_readers,
    create_transformers,
    create_writers,
    parse_config,
    run_harvest,
)
from oarepo_oaipmh_harvester.report import HarvestReport, send_harvest_report

__all__ = [
    "RunAllHarvesters",
    "create_readers",
    "create_transformers",
    "create_writers",
    "format_oaipmh_datestamp",
    "harvest_oaipmh_records",
    "harvest_window",
    "parse_config",
    "run_all_harvesters",
    "run_harvest",
]


@shared_task
def harvest_oaipmh_records(  # noqa: PLR0913 mirrors the task arguments
    *,
    harvester_id: str,
    oai_ids: list[str] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    batch_size: int | None = None,
    parallel: bool = False,
) -> None:
    """Harvest OAI-PMH records for the given harvester, then mail a report to its harvest managers.

    `parallel` harvests everything in windows dispatched as subtask runs; it needs to run as a
    job run and can not select `oai_ids`. Such a harvest returns here - its report is sent by
    the window that finishes last.
    """
    harvester = OAIHarvesterAggregate.get_record(harvester_id)
    if parallel and start_parallel_harvest(harvester, oai_ids):
        return

    report = HarvestReport()
    try:
        run_harvest(harvester, report, oai_ids=oai_ids, since=since, until=until, batch_size=batch_size)
    except Exception as e:
        report.error = f"{type(e).__name__}: {e}"
        raise
    finally:
        report.finished_at = datetime.now(UTC)
        try:
            send_harvest_report(harvester, report)
        except Exception:
            # the report must not hide the harvest's own outcome
            current_app.logger.exception("Could not send the report of harvester %s", harvester_id)


@shared_task(ignore_result=True)
def run_all_harvesters() -> None:
    """Run all OAI-PMH harvester tasks."""
    harvesters = OAIHarvester.query.all()
    for harvester in harvesters:
        try:
            current_app.logger.info("Started harvesting %s", harvester.id)
            harvest_oaipmh_records(harvester_id=harvester.id)
            current_app.logger.info("Successfully harvested %s", harvester.id)
        except Exception:  # pragma: no cover
            current_app.logger.exception("Exception during harvesting %s", harvester.id)


class RunAllHarvesters(JobType):
    """A job type to run invenio CLI commands as Celery tasks."""

    id = "run_all_harvesters"
    title = "Run all harvester tasks"
    description = "Run all harvester tasks."
    task = run_all_harvesters
