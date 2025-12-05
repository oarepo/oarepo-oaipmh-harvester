#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""OAI Import Transformer for OAI-PMH harvested records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import oaipmh_scythe
from invenio_vocabularies.datastreams.datastreams import StreamEntry
from invenio_vocabularies.datastreams.errors import TransformerError
from invenio_vocabularies.datastreams.transformers import BaseTransformer
from lxml import etree  # type: ignore[reportAttributeAccessIssue]
from oarepo_runtime import current_runtime

if TYPE_CHECKING:
    from oarepo_runtime.api import Import


class OAIImportTransformer(BaseTransformer):
    """Transformer for importing OAI-PMH records.

    This transformers needs a model name to find the appropriate importer
    for the metadata format being imported.
    """

    def __init__(self, model: str, *_args: Any, **_kwargs: Any) -> None:
        """Initialize the OAI import transformer."""
        super().__init__()
        self.model = model

    def apply(self, stream_entry: StreamEntry, *_args: Any, **_kwargs: Any) -> StreamEntry:
        """Apply the transformation to the entry.

        :returns: A StreamEntry. The transformed entry.
                  Raises TransformerError in case of errors.
        """
        if not isinstance(stream_entry.entry, dict) or not isinstance(
            stream_entry.entry["record"],
            oaipmh_scythe.models.Record,  # type: ignore[reportAttributeAccessIssue]
        ):
            raise TransformerError(
                "OAIImport transformer requires entries to be oaipmh_scythe Record instances, "
                f"it is {type(stream_entry)}."
            )
        if stream_entry.entry["record"].header.deleted:
            # deleted record, nothing to import
            return StreamEntry(
                entry={"record": None, "oai_record": stream_entry.entry["record"]},
                op_type=stream_entry.op_type,
            )
        # parse the metadata via the appropriate importer
        metadata_elem = self._get_metadata_element(stream_entry.entry["record"].xml)
        q = etree.QName(metadata_elem)
        namespace_uri = q.namespace
        local_name = q.localname
        imp = self._find_importer(namespace_uri, local_name)
        if xml_deserializer := getattr(imp.deserializer, "deserialize_xml", None):
            # if the deserializer can natively handle XML elements, use that
            data = xml_deserializer(metadata_elem)
        else:
            # otherwise convert to string and use the default deserialize method
            data = imp.deserializer.deserialize(etree.tostring(metadata_elem, encoding=str))
        return StreamEntry(
            entry={"record": data, "oai_record": stream_entry.entry["record"]},
            op_type=stream_entry.op_type,
        )

    def _find_importer(self, namespace_uri: str, local_name: str) -> Import:
        """Find the appropriate importer for the given OAI element."""
        for imp in current_runtime.models[self.model].imports:
            if not imp.oai_name:
                continue
            if imp.oai_name == (namespace_uri, local_name):
                return imp
        raise TransformerError(
            f"No import found for OAI element {{{namespace_uri}}}{local_name} in model {self.model}."
        )

    def _get_metadata_element(self, record_xml: etree._Element) -> etree._Element:
        """Extract the metadata element from an oaipmh_scythe Record XML.

        look for {http://www.openarchives.org/OAI/2.0/}record /
        {http://www.openarchives.org/OAI/2.0/}metadata and get the first child
        """
        oai_metadata_elem = record_xml.find("{http://www.openarchives.org/OAI/2.0/}metadata")
        if oai_metadata_elem is None:
            raise TransformerError("No metadata element found in OAI record.")
        children = [x for x in oai_metadata_elem if x.tag]
        if not children:
            raise TransformerError("No metadata child elements found in OAI record.")
        if len(children) > 1:
            raise TransformerError("Multiple metadata child elements found in OAI record.")
        return children[0]
