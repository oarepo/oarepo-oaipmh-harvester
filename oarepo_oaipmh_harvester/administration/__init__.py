# SPDX-FileCopyrightText: 2024-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""invenio-administration views for harvesters and harvest records.

The views are registered via the `invenio_administration.views` entry point. Access is
granted to administrators and to harvest managers of any harvester (see
`oai_harvester_permissions_decorator`); what each user sees is then limited by the
service permission policies.
"""

from __future__ import annotations
