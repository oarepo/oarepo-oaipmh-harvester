from invenio_db import db
from invenio_users_resources.records.api import UserAggregate


class UserRelationResult(RelationResult):

    def resolve(self, id_, data=None):
        """Resolve the value using the record class."""
        # TODO: handle permissions here !!!!!!

        cache_key = ("users", id_)
        if cache_key in self.cache:
            obj = self.cache[cache_key]
            return obj

        try:
            obj = UserAggregate.get_record(id_)
            db.session.expunge(obj.model.model_obj)
            self.cache[cache_key] = obj
            return obj
        except Exception as e:
            raise InvalidRelationError(
                f"Repository object {cache_key} has not been found or there was an exception accessing it. "
                f"Referenced from {self.field.key}.",
                related_id=id_,
                location=self.field.key,
            ) from e

    def _needs_update_relation_value(self, relation: LookupResult):
        # Don't dereference if already referenced.
        return "@v" not in relation.value

    def _add_version_info(self, data, relation: LookupResult, resolved_object):
        data["@v"] = f"{resolved_object.id}::{resolved_object.revision_id}"


class UserRelation(Relation):
    result_cls = UserRelationResult

    def __init__(self, key=None, pid_field=None, **kwargs):
        super().__init__(key=key, **kwargs)
        self.pid_field = pid_field
