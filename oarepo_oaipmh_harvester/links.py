#
# Copyright (c) 2025 CESNET z.s.p.o.
#
# This file is a part of oarepo-oaipmh-harvester (see https://github.com/oarepo/oarepo-oaipmh-harvester).
#
# oarepo-oaipmh-harvester is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
#
"""Links for OAI-PMH Harvester."""

from __future__ import annotations

from typing import Any


class ActionLinks:
    """Action links for OAI-PMH Harvester.

    Normally contains a "harvest" link, but can be extended by other links.
    """

    def __init__(self, actions_links: dict[str, Any]):
        """Initialize the ActionLinks."""
        self._actions_links = actions_links

    def should_render(self, obj: Any, ctx: Any) -> bool:  # noqa ARG002
        """Determine if the link should be rendered."""
        return True

    @staticmethod
    def vars(obj: Any, vars: Any) -> None:  # noqa ARG002
        """Overwrite this method in subclasses."""

    def expand(self, obj: Any, context: Any) -> dict[str, Any]:
        """Expand the URI Template."""
        ret = {}
        for action, link in self._actions_links.items():
            if link.should_render(obj, context):
                ret[action] = link.expand(obj, context)
        return ret
