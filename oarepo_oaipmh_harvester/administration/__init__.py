#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""invenio-administration views for harvesters and harvest records.

The views are registered via the ``invenio_administration.views`` entry point. Access is
granted to administrators and to harvest managers of any harvester (see
``oai_harvester_permissions_decorator``); what each user sees is then limited by the
service permission policies.
"""

from __future__ import annotations
