from marshmallow import post_dump


class BaseOaiRecordSchema(BaseRecordSchema):
    @post_dump
    def process_transformers(self, data, **kwargs):
        error_str = ""
        for e in data["errors"]:
            if "location" in e:
                error_str = error_str + f'{e["location"]}: '
            if "message" in e:
                error_str = error_str + f'{e["message"]} - '
            if "info" in e:
                error_str = error_str + f'{e["info"]}, '
        data["errors"] = error_str
        return data
