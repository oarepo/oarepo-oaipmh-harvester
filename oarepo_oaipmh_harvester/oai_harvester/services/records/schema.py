import marshmallow as ma
from invenio_accounts.models import User
from marshmallow import ValidationError, post_dump, pre_load
from marshmallow import fields as ma_fields
from marshmallow.fields import String


def parse_top_level_components(input_string, field_name):
    components = []
    current_component = []
    bracket_level = 0

    for char in input_string:
        if char == "{":
            bracket_level += 1
            current_component.append(char)
        elif char == "}":
            if bracket_level == 0:
                raise ValidationError(
                    "Unmatched brackets in input string",
                    field_name=field_name,
                )
            bracket_level -= 1
            current_component.append(char)
        elif char == "," and bracket_level == 0:
            components.append("".join(current_component).strip())
            current_component = []
        else:
            current_component.append(char)

    # Add the last component
    if current_component:
        components.append("".join(current_component).strip())

    if bracket_level != 0:
        raise ValidationError(
            "Unmatched brackets in input string",
            field_name=field_name,
        )

    return components


class OaiHarvesterSchema(BaseRecordSchema):
    class Meta:
        unknown = ma.RAISE

    baseurl = ma_fields.String(required=True)

    batch_size = ma_fields.Integer()

    code = ma_fields.String(required=True)

    comment = ma_fields.String()

    harvest_managers = ma_fields.List(
        ma_fields.Nested(lambda: HarvestManagersItemSchema())
    )

    loader = ma_fields.String()

    max_records = ma_fields.Integer()

    metadataprefix = ma_fields.String(required=True)

    name = ma_fields.String(required=True)

    setspecs = ma_fields.String(required=True)

    transformers = ma_fields.List(ma_fields.String(), required=True)

    writers = ma_fields.List(ma_fields.String())

    @pre_load
    def remove_schema(self, data, **kwargs):
        data.pop("_schema", None)
        return data

    @pre_load
    def process_transformers(self, data, **kwargs):
        transformers = data.get("transformers")
        batch_size = data.get("batch_size")
        max_records = data.get("max_records")
        if isinstance(transformers, str):
            data["transformers"] = parse_top_level_components(
                transformers, "transformers"
            )
        if batch_size == "":
            data.pop("batch_size")
        if max_records == "":
            data.pop("max_records")
        return data

    @pre_load
    def process_writers(self, data, **kwargs):
        writers = data.get("writers")
        if isinstance(writers, str):
            data["writers"] = parse_top_level_components(writers, "writers")
        return data

    @pre_load
    def load_harvest_managers(self, data, **kwargs):
        # must be a list of email addresses at the beginning
        harvest_managers = data.get("harvest_managers", [])
        if isinstance(harvest_managers, str):
            harvest_managers = parse_top_level_components(
                harvest_managers, "harvest_managers"
            )
        # for each manager, find a user with that email
        # and replace the email with the user id
        harvest_managers_ids = []
        for email in harvest_managers:
            email = email.strip().lower()
            if not email:
                continue
            user = User.query.filter_by(email=email).first()
            if not user:
                raise ValidationError(
                    f"User with email {email} not found", field_name="harvest_managers"
                )
            harvest_managers_ids.append(
                {
                    "id": user.id,
                    "email": user.email,
                }
            )
        data["harvest_managers"] = harvest_managers_ids
        return data

    @post_dump
    def dump_harvest_managers(self, data, **kwargs):
        # must be a list of user ids at the beginning
        harvest_managers = data.get("harvest_managers", [])
        if not harvest_managers:
            return data
        # for each manager, find a user with that id
        # and replace the id with the email
        data["harvest_managers"] = [x["email"] for x in harvest_managers]
        return data


class HarvestManagersItemSchema(DictOnlySchema):
    class Meta:
        unknown = ma.INCLUDE

    _id = ma_fields.Integer(data_key="id", attribute="id")

    _version = String(data_key="@v", attribute="@v")

    email = ma_fields.String()
