# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Splitting a parallel harvest into the time windows its tasks harvest.

[WindowPlanner.plan][oarepo_oaipmh_harvester.planning.WindowPlanner.plan] asks the source how
many records `[earliestDatestamp, now]` holds and then halves the windows by time until each
one holds about `OAI_HARVESTER_PARALLEL_TARGET_SIZE` records, so that a burst of records (a
mass import, say) does not make one window much slower than all the others. It cannot split
below the granularity of the source, so a burst within one day of a date-only source stays
one window - it is logged and harvested as one.

A [Window][oarepo_oaipmh_harvester.planning.Window] is a pair of inclusive bounds, as
OAI-PMH's `from` and `until` are. The windows do not overlap, every record falls in exactly
one of them, and a range without records gets no window.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flask import current_app

from oarepo_oaipmh_harvester.oai_source import OAIPMHSource, floor_to


@dataclass(frozen=True, order=True)
class Window:
    """Time range of a parallel harvest; both ends inclusive (UTC), as OAI-PMH `from` / `until`."""

    start: datetime
    end: datetime


_WINDOW_LENGTHS = {
    "s": timedelta(seconds=1),
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
}


def _parse_window_length(value: str) -> timedelta:
    """Parse a window length such as `30m`, `6h` or `1d`."""
    unit = _WINDOW_LENGTHS.get(value[-1:])
    if unit is None or not value[:-1].isdigit():
        raise ValueError(f"Invalid window length {value!r}, expected e.g. '30m', '6h' or '1d'")
    return int(value[:-1]) * unit


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


class WindowPlanner:
    """Splits the whole range of a source into windows the harvest can run in parallel.

    The limits default to `OAI_HARVESTER_PARALLEL_TARGET_SIZE`, `_FIXED_WINDOW` and
    `_MAX_WINDOWS` of the application config; `fixed_window` is the length used when the
    source does not report how many records a range has.
    """

    def __init__(
        self,
        source: OAIPMHSource,
        *,
        target_size: int | None = None,
        fixed_window: str | timedelta | None = None,
        max_windows: int | None = None,
    ):
        """Remember the source and the limits - nothing is requested until `plan`."""
        config = current_app.config
        self.source = source
        self.target_size = target_size or config["OAI_HARVESTER_PARALLEL_TARGET_SIZE"]
        self.fixed_window = (
            fixed_window
            if isinstance(fixed_window, timedelta)
            else _parse_window_length(fixed_window or config["OAI_HARVESTER_PARALLEL_FIXED_WINDOW"])
        )
        self.max_windows = max_windows or config["OAI_HARVESTER_PARALLEL_MAX_WINDOWS"]
        self.known_nonempty = False
        """Whether the windows were counted by the source, i.e. none of them was empty."""

    def plan(self) -> list[Window]:
        """Split `[earliestDatestamp, now]` into windows; empty when the source has no records."""
        started = time.monotonic()
        unit = self.source.unit
        start = self.source.earliest
        end = floor_to(datetime.now(UTC), unit)
        if end < start:
            return []
        whole = Window(start, end)
        total = self.source.count(start, end)
        self.known_nonempty = total is not None
        if total == 0:
            return []
        windows = self._fixed(whole) if total is None else self._split(whole, total)
        current_app.logger.info(
            "Split %s (%s records) into %s windows using %s request(s) in %.1f s",
            self.source.base_url,
            "unknown" if total is None else total,
            len(windows),
            self.source.probes,
            time.monotonic() - started,
        )
        return windows

    def _fixed(self, whole: Window) -> list[Window]:
        """Consecutive windows of `fixed_window` length, longer when there would be too many."""
        unit = self.source.unit
        units = (whole.end - whole.start) // unit + 1
        per = max(int(self.fixed_window // unit), _ceil_div(units, self.max_windows), 1)
        return [
            Window(whole.start + i * unit, min(whole.start + (i + per - 1) * unit, whole.end))
            for i in range(0, units, per)
        ]

    def _split(self, whole: Window, total: int) -> list[Window]:
        """Breadth-first halving of the windows that hold more than `target_size` records."""
        unit = self.source.unit
        result: list[Window] = []
        queue: deque[tuple[Window, int]] = deque([(whole, total)])
        while queue:
            window, size = queue.popleft()
            # both ends are inclusive - a window one unit long already holds two units of the source
            splittable = window.end - window.start >= unit
            if size <= self.target_size or not splittable or len(result) + len(queue) + 2 > self.max_windows:
                if size > self.target_size:
                    current_app.logger.warning(
                        "Window %s - %s of %s records can not be split further, harvesting it as one",
                        window.start.isoformat(),
                        window.end.isoformat(),
                        size,
                    )
                result.append(window)
                continue
            half = unit * ((window.end - window.start) // (2 * unit))
            left = Window(window.start, window.start + half)
            right = Window(left.end + unit, window.end)
            for part in (left, right):
                part_size = self.source.count(part.start, part.end)
                if part_size is None:
                    # the source stopped telling the size - do not split this part any further
                    part_size = self.target_size
                if part_size:
                    queue.append((part, part_size))
        return sorted(result)
