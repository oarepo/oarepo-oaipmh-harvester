from invenio_records_resources.services.records.results import RecordItem, RecordList


class OaiHarvesterRecordItem(RecordItem):
    """OaiHarvesterRecord record item."""

    components = [*RecordItem.components]


class OaiHarvesterRecordList(RecordList):
    """OaiHarvesterRecord record list."""

    components = [*RecordList.components]
