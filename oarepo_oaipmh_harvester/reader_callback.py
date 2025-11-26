from invenio_db import db

from oarepo_oaipmh_harvester.models import OAIHarvesterRun


def reader_callback(batch: StreamBatch, *, identity, oai_run, manual, oai_harvester):
    for e in batch.entries:
        e.context["manual"] = manual
    run = OAIHarvesterRun.query.filter_by(id=oai_run).with_for_update().one()
    run.records += len(batch.entries)
    db.session.add(run)
    db.session.commit()
    return batch
