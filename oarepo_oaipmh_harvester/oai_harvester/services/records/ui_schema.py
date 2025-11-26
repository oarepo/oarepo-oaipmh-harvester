import marshmallow as ma
from marshmallow import fields as ma_fields
from marshmallow.fields import String


class OaiHarvesterUISchema(InvenioUISchema):
    class Meta:
        unknown = ma.RAISE

    baseurl = ma_fields.String(required=True)

    batch_size = ma_fields.Integer()

    code = ma_fields.String(required=True)

    comment = ma_fields.String()

    deletion_status = ma_fields.String()

    harvest_managers = ma_fields.List(
        ma_fields.Nested(lambda: HarvestManagersItemUISchema())
    )

    is_deleted = ma_fields.Boolean()

    is_published = ma_fields.Boolean()

    loader = ma_fields.String()

    max_records = ma_fields.Integer()

    metadataprefix = ma_fields.String(required=True)

    name = ma_fields.String(required=True)

    setspecs = ma_fields.String(required=True)

    transformers = ma_fields.List(ma_fields.String(), required=True)

    version_id = ma_fields.Integer()

    writers = ma_fields.List(ma_fields.String())


class HarvestManagersItemUISchema(DictOnlySchema):
    class Meta:
        unknown = ma.INCLUDE

    _id = ma_fields.Integer(data_key="id", attribute="id")

    _version = String(data_key="@v", attribute="@v")

    email = ma_fields.String()
