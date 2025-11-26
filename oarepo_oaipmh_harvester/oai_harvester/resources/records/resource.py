from flask import g
from flask_resources import resource_requestctx, route
from invenio_records_resources.proxies import current_service_registry
from invenio_records_resources.resources import RecordResource
from invenio_records_resources.resources.records.resource import request_view_args


class OaiHarvesterResource(RecordResource):
    """OaiHarvesterRecord resource."""

    def create_url_rules(self):
        """Create the URL rules for the record resource."""
        routes = self.config.routes
        url_rules = super().create_url_rules()
        url_rules.append(route("POST", routes["harvest"], self.harvest))
        return url_rules

    @property
    def api_service(self):
        return current_service_registry.get(self.config.api_service)

    @request_view_args
    def harvest(self, *args, **kwargs):
        return self.api_service.start_harvest(
            g.identity, resource_requestctx.view_args["pid_value"]
        )
