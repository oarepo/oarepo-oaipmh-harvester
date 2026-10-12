# SPDX-FileCopyrightText: 2023-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Writers for OAI-PMH harvested records.

This package ships the [oai-service][oarepo_oaipmh_harvester.writers.oai_service] writer,
which brings the local records to the harvested state through the model's service and
keeps a harvest record for every harvested OAI identifier.

What the harvest record contains, how errors are stored and how to write additional
writers is described in [Readers, transformers and writers](../../readers-transformers-writers.md).
"""

from __future__ import annotations

from .oai_service import OAIServiceWriter

__all__ = ["OAIServiceWriter"]
