from invenio_pidstore.providers.recordid_v2 import RecordIdProviderV2
from invenio_records.dumpers import SearchDumper
from invenio_records.systemfields import ConstantField
from invenio_records_resources.records.api import Record as InvenioRecord
from invenio_records_resources.records.systemfields import IndexField
from invenio_records_resources.records.systemfields.pid import PIDField, PIDFieldContext

from oarepo_oaipmh_harvester.oai_harvester.records.models import OaiHarvesterMetadata
from oarepo_oaipmh_harvester.records.relations import UserRelation


class OaiHarvesterIdProvider(RecordIdProviderV2):
    pid_type = "hrvstr"


class OaiHarvesterRecord(InvenioRecord):

    model_cls = OaiHarvesterMetadata

    schema = ConstantField("$schema", "local://oai_harvester-1.0.0.json")

    index = IndexField(
        "oarepo-oaipmh-harvester-oai_harvester-1.0.0",
    )

    pid = PIDField(
        provider=OaiHarvesterIdProvider, context_cls=PIDFieldContext, create=True
    )

    dumper = SearchDumper()

    relations = RelationsField(
        harvest_managers=UserRelation(
            "harvest_managers",
            keys=["id", "email"],
            pid_field=None,
        ),
    )
