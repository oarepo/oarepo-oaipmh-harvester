# SPDX-FileCopyrightText: 2023-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Transformers for OAI-PMH harvested records.

A transformer converts what the harvester's reader yields into the data the writer
stores - `{"record": <data for the model's service or None>, "oai_record": <OAI record>}`.
This package ships [oai-import][oarepo_oaipmh_harvester.transformers.oai_import], which
converts the metadata with one of the target model's imports.

How to write your own readers and transformers, what they receive and produce and how
they report errors is described in
[Readers, transformers and writers](../../readers-transformers-writers.md).
"""

from __future__ import annotations

from .oai_import import OAIImportTransformer

__all__ = ["OAIImportTransformer"]
