# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Running a harvest in parallel windows as subtask runs of an invenio-jobs run.

[start_parallel_harvest][oarepo_oaipmh_harvester.parallel.start_parallel_harvest] plans the
windows ([WindowPlanner][oarepo_oaipmh_harvester.planning.WindowPlanner]), creates a subtask
run for each of them and dispatches
[harvest_window][oarepo_oaipmh_harvester.parallel.harvest_window]. The parent task returns
as soon as they are dispatched, so the run stays `RUNNING` until its windows finish it.

A window harvests its range with
[run_harvest][oarepo_oaipmh_harvester.pipeline.run_harvest], finalizes its subtask run
(`finalize_subtask` of invenio-jobs counts the entries on the parent) and the window that
finishes last mails the report of the whole run. The window tasks never raise - a subtask
run left `QUEUED` or `RUNNING` would keep the parent run `RUNNING` forever.

**Stopping.** `RunService.stop` only sets the parent `CANCELLING` and revokes the parent task,
which has already returned. `finalize_subtask` overwrites the parent status on every call, so
[ParallelHarvest.stopped][oarepo_oaipmh_harvester.parallel.ParallelHarvest.stopped] keeps the
stop in the cache: the windows that have not started yet check it and skip their harvest, and
when the last window finishes, the run is set `CANCELLED` and a report saying it was stopped
is sent. A run stopped before its windows were created (while it waited or was planning)
does not start at all - the report is sent and the task raises `TaskExecutionPartialError`,
so the run ends `PARTIAL_SUCCESS` with the message "The run was stopped before the harvest
started" (`execute_run` would otherwise mark it `SUCCESS`). The same status is the result
when all windows finished before the parent task returned (eager celery, tiny runs).
Two gaps remain - a window that finishes at the moment of the stop can overwrite
`CANCELLING` before any other window reads it (the harvest then goes on), and a window that
is already running is not interrupted. With eager celery the parent task finishes the run
itself and `execute_run` writes the final status afterwards.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import sqlalchemy as sa
from celery.app import shared_task
from flask import current_app
from invenio_access.permissions import system_identity
from invenio_cache import current_cache
from invenio_db import db
from invenio_jobs.errors import TaskExecutionPartialError
from invenio_jobs.logging.jobs import EMPTY_JOB_CTX, job_context, set_job_context
from invenio_jobs.models import Run, RunStatusEnum
from invenio_jobs.proxies import current_runs_service

from oarepo_oaipmh_harvester.oai_harvester.api import OAIHarvesterAggregate
from oarepo_oaipmh_harvester.oai_source import OAIPMHSource, parse_datestamp
from oarepo_oaipmh_harvester.pipeline import create_readers, run_harvest
from oarepo_oaipmh_harvester.planning import Window, WindowPlanner
from oarepo_oaipmh_harvester.report import HarvestReport, send_harvest_report

_STOPPED_KEY = "oai-harvest-stopped:{}"
_REPORT_KEY = "oai-harvest-report:{}"
_MEMORY_TIMEOUT = 7 * 24 * 3600
"""How long the stop flag and the report claim are kept, in seconds."""


def start_parallel_harvest(harvester: OAIHarvesterAggregate, oai_ids: list[str] | None) -> bool:
    """Start the harvest as window subtask runs; False when it has to be harvested sequentially.

    A parallel harvest needs a job run (for the subtask runs) and the `oai-pmh` loader (to be
    splittable by time); it always harvests everything, so selected identifiers are rejected.
    Returns True as soon as the windows are dispatched - the report and the run status are
    then handled by the window that finishes last. Raises `TaskExecutionPartialError` when
    the run was stopped before anything was harvested.
    """
    ctx = cast("dict[str, str]", job_context.get())
    if oai_ids or ctx is EMPTY_JOB_CTX:
        current_app.logger.warning(
            "Parallel harvest of %s is not a job run or selects records - harvesting sequentially", harvester.id
        )
        return False
    readers_config = create_readers(harvester)
    if readers_config["type"] != "oai-pmh":
        current_app.logger.warning(
            "Parallel harvest of %s needs the oai-pmh loader, it has %s - harvesting sequentially",
            harvester.id,
            readers_config["type"],
        )
        return False
    harvest = ParallelHarvest(harvester.id, job_id=ctx["job_id"], run_id=ctx["run_id"])
    # planning a large or slow source takes minutes - do not plan a run that is stopped already
    harvest.abort_if_stopped()
    reader_args = readers_config["args"]
    planner = WindowPlanner(
        OAIPMHSource(
            reader_args["base_url"],
            metadata_prefix=reader_args.get("metadata_prefix"),
            set_=reader_args.get("set"),
        )
    )
    try:
        windows = planner.plan()
    except Exception:
        current_app.logger.exception(
            "Could not split the harvest of %s into windows - harvesting sequentially", harvester.id
        )
        return False
    harvest.dispatch(windows, known_nonempty=planner.known_nonempty)
    return True


class ParallelHarvest:
    """The windows of one harvest and the job run they are the subtasks of.

    Built from the harvester id, not the aggregate, so that a window task can resolve the
    harvester inside its own error handling.
    """

    def __init__(self, harvester_id: str, *, job_id: str, run_id: str):
        """Remember the harvester and its run - nothing is requested here."""
        self.harvester_id = harvester_id
        self.job_id = job_id
        self.run_id = run_id
        self._harvester: OAIHarvesterAggregate | None = None

    @property
    def harvester(self) -> OAIHarvesterAggregate:
        """The harvester of the run (loaded on first use)."""
        if self._harvester is None:
            self._harvester = OAIHarvesterAggregate.get_record(self.harvester_id)
        return self._harvester

    def dispatch(self, windows: list[Window], *, known_nonempty: bool) -> None:
        """Create a subtask run per window, dispatch the window tasks and finish a run that is done.

        `known_nonempty` says that the planner counted the windows, so they do not have to be
        probed before harvesting. Raises `TaskExecutionPartialError` when the run was stopped
        (also during the planning that precedes this call) - the windows would only skip.
        """
        # the stop may have come during the planning
        self.abort_if_stopped()
        if not windows:
            current_app.logger.info("No records to harvest for %s", self.harvester_id)
            return
        subtask_ids = [
            str(
                current_runs_service.create_subtask_run(
                    system_identity,
                    self.run_id,
                    self.job_id,
                    args={"from": window.start.isoformat(), "until": window.end.isoformat()},
                ).id
            )
            for window in windows
        ]
        # all subtasks must exist (and be closed) before any of them can finish - the last one
        # finishing would otherwise finish the run while more subtasks are still to be created
        db.session.execute(sa.update(Run).where(Run.id == self.run_id).values(subtasks_closed=True))
        db.session.commit()
        queue = current_app.config["OAI_HARVESTER_WINDOW_QUEUE"]
        routing = {"queue": queue} if queue else {}
        for window, subtask_id in zip(windows, subtask_ids, strict=True):
            harvest_window.apply_async(
                kwargs={
                    "harvester_id": self.harvester_id,
                    "job_id": self.job_id,
                    "parent_run_id": self.run_id,
                    "subtask_run_id": subtask_id,
                    "start": window.start.isoformat(),
                    "end": window.end.isoformat(),
                    "known_nonempty": known_nonempty,
                },
                **routing,
            )
        current_app.logger.info("Harvest of %s split into %s windows", self.harvester_id, len(windows))
        self.finish_if_all_windows_done()

    def harvest_window(self, *, subtask_run_id: str, start: datetime, end: datetime, known_nonempty: bool) -> None:
        """Harvest one window as its subtask run - never raises."""
        report = HarvestReport()
        success = False
        stopped = False
        try:
            stopped = self.stopped()
            if stopped:
                current_app.logger.info(
                    "Window %s - %s of %s skipped, the run was stopped", start, end, self.harvester_id
                )
                success = True
            else:
                current_runs_service.start_processing_subtask(system_identity, subtask_run_id, self.job_id)
                run_harvest(
                    self.harvester,
                    report,
                    oai_ids=None,
                    since=start,
                    until=end,
                    batch_size=None,
                    # indexing the harvest records one by one is expensive for a large
                    # harvest - they are indexed by the beat that drains the bulk queue
                    writer_overrides={"sync_index": False},
                    probe=not known_nonempty,
                )
                success = True
        except Exception:
            current_app.logger.exception("Window %s - %s of harvester %s failed", start, end, self.harvester_id)
            db.session.rollback()
        if not stopped:
            try:
                # finalize_subtask overwrites the parent status - remember a stop while it shows
                self.stopped()
            except Exception:
                current_app.logger.exception("Could not check whether the run %s was stopped", self.run_id)
        try:
            current_runs_service.finalize_subtask(
                system_identity,
                subtask_run_id,
                self.job_id,
                success=success,
                errored_entries_count=report.failed,
                inserted_entries_count=report.created,
                updated_entries_count=report.updated,
            )
        except Exception:
            current_app.logger.exception("Could not finalize the window %s - %s", start, end)
            db.session.rollback()
        try:
            self.send_report_if_finished()
        except Exception:
            current_app.logger.exception("Could not finish the run %s", self.run_id)
            db.session.rollback()

    def stopped(self) -> bool:
        """Whether the run was stopped; keeps the stop for the windows that have not started yet.

        `finalize_subtask` overwrites the parent status on every call (`CANCELLING` included),
        so the first window that sees the stop stores it in the cache; a window that finishes
        without having seen it checks once more right before finalizing, which is the last
        moment the status still shows the stop.
        """
        if current_cache.get(_STOPPED_KEY.format(self.run_id)):
            return True
        parent = db.session.get(Run, self.run_id)
        stopped = parent is not None and parent.status in (RunStatusEnum.CANCELLING, RunStatusEnum.CANCELLED)
        if stopped:
            current_cache.set(_STOPPED_KEY.format(self.run_id), 1, timeout=_MEMORY_TIMEOUT)
        return stopped

    def finish_if_all_windows_done(self) -> None:
        """Finish a run whose windows all ended before the parent task returned (eager celery, tiny harvests).

        `finalize_subtask` has already finished the run and sent the jobs notification; raising
        makes `execute_run` keep the `PARTIAL_SUCCESS` it computed instead of overwriting it
        with `SUCCESS`. It sends the notification once more - harvester jobs normally have none.
        """
        db.session.expire_all()
        parent = db.session.get(Run, self.run_id)
        if parent is None or parent.completed_subtasks < parent.total_subtasks:
            return  # the last window finishes the run
        self.send_report_if_finished()
        if self.stopped():
            # the skipped windows counted as successful, so no counter shows the stop - without
            # this `execute_run` would mark the run SUCCESS although the user stopped it
            raise TaskExecutionPartialError(
                "The run was stopped before all of its windows finished", errored_entries_count=0
            )
        if parent.failed_subtasks or parent.errored_entries:
            raise TaskExecutionPartialError(
                f"{parent.failed_subtasks} of {parent.total_subtasks} windows failed, "
                f"{parent.errored_entries} records with errors",
                errored_entries_count=0,  # already counted by finalize_subtask
            )

    def send_report_if_finished(self) -> None:
        """Mail the report of the run, exactly once, when all of its windows have finished."""
        db.session.expire_all()
        parent = db.session.get(Run, self.run_id)
        if parent is None or parent.completed_subtasks < parent.total_subtasks:
            return  # other windows are still running
        # `add` sets the key only if it does not exist, so exactly one caller reports - claim it
        # before doing the work only that caller needs
        if not current_cache.add(_REPORT_KEY.format(self.run_id), 1, timeout=_MEMORY_TIMEOUT):
            return
        try:
            report = HarvestReport.from_run(self.harvester, parent)
            if self.stopped():
                self._mark_cancelled()
                report.stopped = True
                report.error = (
                    "The run was stopped before all of its windows finished, "
                    "the records of the windows that did not start were not harvested."
                )
            send_harvest_report(self.harvester, report)
        except Exception:
            current_app.logger.exception("Could not send the report of run %s", self.run_id)

    def abort_if_stopped(self) -> None:
        """Before any window was created: if the run was stopped, report it and raise.

        Raising `TaskExecutionPartialError` makes `execute_run` end the run `PARTIAL_SUCCESS`
        with the message below - without it the run would end `SUCCESS`, and the only status
        that means "stopped", `CANCELLED`, is set by `execute_run` for `SystemExit`, which a
        task running in a celery worker must not raise.
        """
        if not self.stopped():
            return
        message = "The run was stopped before the harvest started"
        current_app.logger.info("Harvest of %s not started: %s", self.harvester_id, message)
        self.send_report_if_finished()
        raise TaskExecutionPartialError(message, errored_entries_count=0)

    def _mark_cancelled(self) -> None:
        """Set the run `CANCELLED` - `finalize_subtask` marked it successful, the windows were skipped."""
        db.session.execute(
            sa.update(Run)
            .where(Run.id == self.run_id)
            .values(status=RunStatusEnum.CANCELLED, finished_at=datetime.now(UTC))
        )
        db.session.commit()


@shared_task(
    bind=True,
    ignore_result=True,
    # the name stays the same although the task moved out of tasks.py - windows queued by an
    # older deployment must still be picked up
    name="oarepo_oaipmh_harvester.tasks.harvest_window",
)
def harvest_window(  # noqa: PLR0913 one keyword argument per window bound
    self: Any,  # celery passes the task instance
    *,
    harvester_id: str,
    job_id: str,
    parent_run_id: str,
    subtask_run_id: str,
    start: str,
    end: str,
    known_nonempty: bool = False,
) -> None:
    """Harvest one window of a parallel harvest as a subtask run of the job run."""
    with set_job_context(
        {
            "run_id": parent_run_id,
            "job_id": job_id,
            "identity_id": system_identity.id,
            "task_id": self.request.id,
            "parent_task_id": None,
        }
    ):
        ParallelHarvest(harvester_id, job_id=job_id, run_id=parent_run_id).harvest_window(
            subtask_run_id=subtask_run_id,
            start=parse_datestamp(start),
            end=parse_datestamp(end),
            known_nonempty=known_nonempty,
        )
