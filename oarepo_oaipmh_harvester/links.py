# SPDX-FileCopyrightText: 2025-2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

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
