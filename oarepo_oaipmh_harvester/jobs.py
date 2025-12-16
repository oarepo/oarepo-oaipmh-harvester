#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Jobs for OAI-PMH Harvester."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from invenio_db import db
from invenio_jobs.jobs import JobType
from invenio_jobs.proxies import current_jobs

from oarepo_oaipmh_harvester.oai_harvester.models import OAIHarvester

from .tasks import harvest_oaipmh_records

if TYPE_CHECKING:
    from datetime import datetime

    from invenio_jobs.models import Job


class OAIHarvestJob(JobType):
    """OAI Harvester Job."""

    id = "harvest_oaipmh_records"
    """ID is passed by the subclass when harvester is created.

    Note: jobs do not have parameters, only run parameters, but we need to pass
    harvester_id and passing them as run parameters is not possible when
    scheduling the job from the administration interface. Because of that,
    we create a new subclass of this job for each harvester with the harvester
    code embedded in the job ID.

    The id of the job is then "harvest_oaipmh_records_{harvester_id}" and
    this id is never used.
    """

    title = "OAI Harvester Job"
    """Title is passed by the subclass when harvester is created."""

    description = "Harvester job for OAI-PMH Harvester"
    """Description of the harvester job."""

    task = harvest_oaipmh_records

    @classmethod
    def build_task_arguments(
        cls,
        job_obj: Job,  # noqa ARG003 for interface compatibility
        since: None | datetime = None,
        **kwargs: Any,  # noqa ARG003 for interface compatibility
    ) -> dict:
        """Build task arguments for the job."""
        return {
            "harvester_id": cls.id.replace("harvest_oaipmh_records_", ""),
            "since": since.isoformat() if since else None,
        }


def register_oaipmh_job(harvester_id: str) -> None:
    """Register a new OAI-PMH harvester job.

    Note: current invenio-jobs does not support job parameters, only run parameters.
    Because harvesters are created dynamically in a database and each harvester
    needs its own job (otherwise it would not be possible to schedule them separately),
    we need to create a new job class for each harvester.

    This is done dynamically whenever a new harvester is created or during server startup
    inside the finalize_apps function.
    """
    # create and register the job
    job_id = f"harvest_oaipmh_records_{harvester_id}"
    current_jobs.registry._jobs.pop(job_id, None)  # unregister if exists # noqa SLF001
    current_jobs.registry.register(
        type(
            f"OAIHarvestJob_{job_id}",
            (OAIHarvestJob,),
            {
                "id": job_id,
                "title": f"OAI Harvester Job for harvester {harvester_id}",
            },
        )
    )


def unregister_oaipmh_job(job_id: str) -> None:
    """Unregister an OAI-PMH harvester job."""
    # unregister the job
    current_jobs.registry._jobs.pop(job_id, None)  # noqa SLF001


def register_current_harvesters() -> None:
    """Register jobs for all harvesters stored in the database."""
    try:
        for harvester in db.session.query(OAIHarvester).all():
            register_oaipmh_job(harvester.id)
    # An exception might happen for example during invenio db init when
    # the application is started but the database is not yet initialized.
    # We ignore these exceptions with a general except clause, as different
    # kinds of exceptions might happen depending on the situation.
    # We only re-raise SystemExit and KeyboardInterrupt to allow proper
    # shutdown of the application in case of user interruption.
    except SystemExit:
        raise
    except KeyboardInterrupt:
        raise
    except Exception:  # noqa BLE001
        db.session.rollback()
