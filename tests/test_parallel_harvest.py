# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Parallel harvest - whole job runs started from the command line against the fake source.

Celery is eager in the tests, so the windows of a run are harvested one after another inside
the run; a hook on the source (`source.on`) acts between them - it fails a window, stops the
run or changes the source while the run is in progress.
"""

from __future__ import annotations

import datetime as dt

import pytest
import sqlalchemy as sa
from fake_oai_source import assert_windows_cover, datestamps, timestamp
from invenio_access.permissions import system_identity
from invenio_db import db
from invenio_jobs.logging.jobs import job_context
from invenio_jobs.models import Run, RunStatusEnum

from oarepo_oaipmh_harvester.cli import oai_cli
from oarepo_oaipmh_harvester.planning import Window
from oarepo_oaipmh_harvester.proxies import current_oai_harvester_service
from oarepo_oaipmh_harvester.tasks import harvest_oaipmh_records

pytestmark = pytest.mark.usefixtures("location", "test_model")


@pytest.fixture(scope="module")
def app_config(app_config):
    # one record per window makes the split visible on a source with a handful of records
    app_config["OAI_HARVESTER_PARALLEL_TARGET_SIZE"] = 1
    return app_config


def _harvest(app, *args: str) -> Run:
    """Run `invenio oai harvest test <args>` and return the job run it started."""
    result = app.test_cli_runner().invoke(oai_cli, ["harvest", "test", *args])
    assert result.exit_code == 0, result.output
    db.session.expire_all()
    return db.session.query(Run).filter_by(parent_run_id=None).order_by(Run.created.desc()).first()


def _stop_the_run(_params) -> None:
    """Press *Stop* - what `RunService.stop` does to the run."""
    run_id = job_context.get()["run_id"]
    db.session.execute(sa.update(Run).where(Run.id == run_id).values(status=RunStatusEnum.CANCELLING))
    db.session.commit()


def _once(callback):
    """Call `callback` on the first request only."""
    calls = []

    def hook(params):
        if not calls:
            calls.append(params)
            callback(params)

    return hook


def test_parallel_harvest(app, source, harvester_job, harvest_manager, harvested, outbox):
    source.extend(datestamps())

    run = _harvest(app, "--parallel")

    assert run.status == RunStatusEnum.SUCCESS
    assert 1 < run.total_subtasks == run.completed_subtasks
    assert (run.total_entries, run.inserted_entries, run.errored_entries) == (8, 8, 0)
    assert harvested() == source.identifiers
    # one mail for the whole run, sent by the window that finished last
    assert [mail.subject for mail in outbox] == ["Harvest of Test Harvester finished successfully with 8 ok record(s)"]
    assert_windows_cover(
        [Window(timestamp(sub.args["from"]), timestamp(sub.args["until"])) for sub in run.subtasks], source
    )


def test_failing_window_is_reported(app, source, harvester_job, harvest_manager, harvested, outbox):
    source.extend(datestamps())
    failing = source.records[3]

    def outage(params):
        if source.in_range(failing.datestamp, params):
            raise RuntimeError("the source is down for this range")

    source.on("ListRecords", outage)

    run = _harvest(app, "--parallel")

    assert run.status == RunStatusEnum.PARTIAL_SUCCESS
    assert run.failed_subtasks == 1
    assert harvested() == source.identifiers - {failing.identifier}
    assert len(outbox) == 1
    assert "were not fully harvested" in outbox[0].body


def test_stopping_a_run_skips_the_remaining_windows(app, source, harvester_job, harvest_manager, harvested, outbox):
    source.extend(datestamps())
    # the stop comes while the first window runs - it finishes, the others skip
    source.on("ListRecords", _once(_stop_the_run))

    run = _harvest(app, "--parallel")

    assert run.status == RunStatusEnum.CANCELLED
    assert harvested() == {source.records[0].identifier}
    assert [mail.subject for mail in outbox] == ["Harvest of Test Harvester was stopped"]


def test_a_run_stopped_while_planning_does_not_start(app, source, harvester_job, harvest_manager, harvested, outbox):
    source.extend(datestamps())
    source.on("ListIdentifiers", _once(_stop_the_run))

    run = _harvest(app, "--parallel")

    # invenio-jobs ends a run whose task raised `TaskExecutionPartialError` with PARTIAL_SUCCESS
    assert run.status == RunStatusEnum.PARTIAL_SUCCESS
    assert "stopped before the harvest started" in run.message
    assert run.total_subtasks == 0
    assert harvested() == set()
    assert [mail.subject for mail in outbox] == ["Harvest of Test Harvester was stopped"]


def test_deleting_the_harvester_does_not_hang_the_run(app, source, harvester_job):
    source.extend(datestamps())

    def delete_harvester(_params):
        current_oai_harvester_service.delete(system_identity, "test")
        db.session.commit()

    source.on("ListRecords", _once(delete_harvester))

    run = _harvest(app, "--parallel")

    # every window finished one way or the other, so the run did too
    assert run.completed_subtasks == run.total_subtasks
    assert run.status != RunStatusEnum.RUNNING


def test_window_emptied_after_planning_is_not_a_failure(app, source, harvester_job, harvested):
    source.extend(datestamps())
    moved = source.records[-1]
    tomorrow = (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # the record of the last window is modified at the source while the first window runs -
    # it moves past the planned range, its window finds nothing
    source.on("ListRecords", _once(lambda _params: source.update(moved.identifier, tomorrow)))

    run = _harvest(app, "--parallel")

    assert run.status == RunStatusEnum.SUCCESS
    assert run.failed_subtasks == 0
    assert harvested() == source.identifiers - {moved.identifier}


def test_parallel_without_a_job_run_harvests_sequentially(app, source, harvester, harvested, caplog):
    source.extend(datestamps())

    harvest_oaipmh_records(harvester_id=harvester, parallel=True)

    assert "harvesting sequentially" in caplog.text
    assert harvested() == source.identifiers


def test_parallel_cli_rejects_a_partial_harvest(app, harvester):
    result = app.test_cli_runner().invoke(oai_cli, ["harvest", harvester, "--parallel", "--since", "2025-01-01"])

    assert result.exit_code == 2
    assert "can not be combined" in result.output


def test_use_job_with_identifiers_and_a_date(app, source, harvester_job, harvested):
    """`--use-job` passes the identifiers and a date-only `--since` as run arguments."""
    source.extend(datestamps())

    run = _harvest(app, "oai:test:1", "oai:test:2", "--use-job", "--since", "2025-01-01")

    assert run.args["since"].startswith("2025-01-01T00:00:00")
    assert run.args["oai_ids"] == ["oai:test:1", "oai:test:2"]
    assert harvested() == {"oai:test:1", "oai:test:2"}
