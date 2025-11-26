from invenio_db import db
from invenio_records_resources.services import (
    RecordService as InvenioRecordService,
)
from invenio_records_resources.services.errors import (
    PermissionDeniedError,
    RecordPermissionDeniedError,
)

from oarepo_oaipmh_harvester.oai_run.models import OAIHarvesterRun
from oarepo_oaipmh_harvester.tasks import harvest_task


class OaiHarvesterService(InvenioRecordService):
    def start_harvest(self, identity, id_, **kwargs):
        try:
            record = self.record_cls.pid.resolve(id_)
            self.require_permission(identity, "run_harvest", record=record, **kwargs)
        except PermissionDeniedError:
            raise RecordPermissionDeniedError(action_name="run_harvest", record=record)

        running = (
            db.session.query(OAIHarvesterRun)
            .filter(OAIHarvesterRun.harvester_id == id_)
            .filter(OAIHarvesterRun.status == "running")
            .first()
        )

        if running:
            raise Exception("A harvester is already running for this ID.")

        harvest_task.delay(id_, manual=True)
        return "Harvesting started on the background.", 200
