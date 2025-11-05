"""Facet definitions."""

from invenio_records_resources.services.records.facets import TermsFacet
from oarepo_runtime.i18n import lazy_gettext as _

code = TermsFacet(field="code", label=_("code.label"))

batch_size = TermsFacet(field="batch_size", label=_("batch_size.label"))

harvest_managers_id = TermsFacet(
    field="harvest_managers.id", label=_("harvest_managers/id.label")
)

harvest_managers_email = TermsFacet(
    field="harvest_managers.email", label=_("harvest_managers/email.label")
)

loader = TermsFacet(field="loader", label=_("loader.label"))

max_records = TermsFacet(field="max_records", label=_("max_records.label"))

metadataprefix = TermsFacet(field="metadataprefix", label=_("metadataprefix.label"))

setspecs = TermsFacet(field="setspecs", label=_("setspecs.label"))

transformers = TermsFacet(field="transformers", label=_("transformers.label"))

writers = TermsFacet(field="writers", label=_("writers.label"))
