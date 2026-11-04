# SPDX-FileCopyrightText: 2026 CESNET z.s.p.o
# SPDX-License-Identifier: MIT

"""Planning the windows of a parallel harvest - `WindowPlanner` against the fake source.

The planner is the part of a parallel harvest whose behaviour depends on the shape of the
source's data, so its cases are tested here directly; whole runs are in
`test_parallel_harvest.py`.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fake_oai_source import DAY_GRANULARITY, assert_windows_cover, datestamps

from oarepo_oaipmh_harvester.oai_source import OAIPMHSource
from oarepo_oaipmh_harvester.planning import Window, WindowPlanner

DAYS = [(dt.date(2025, 1, 1) + dt.timedelta(days=offset)).isoformat() for offset in range(30)]


def _plan(*, target_size: int = 10, max_windows: int = 2000) -> list[Window]:
    source = OAIPMHSource("https://example.org/oai", metadata_prefix="oai_dc")
    return WindowPlanner(source, target_size=target_size, fixed_window="1d", max_windows=max_windows).plan()


@pytest.mark.parametrize(
    ("stamps", "source_options", "limits", "check"),
    [
        pytest.param(datestamps(300, days=300), {}, {}, lambda windows: len(windows) > 1, id="evenly-spread"),
        pytest.param(
            DAYS,
            {"granularity": DAY_GRANULARITY},
            {},
            lambda windows: all(w.start.time() == w.end.time() == dt.time.min for w in windows),
            id="whole-days-for-day-granularity",
        ),
        pytest.param(
            DAYS,
            {"granularity": DAY_GRANULARITY, "complete_list_size": False, "page_size": 10},
            {},
            lambda windows: all(w.start == w.end for w in windows),  # the fixed length: one day each
            id="fixed-windows-without-the-size",
        ),
        pytest.param(
            datestamps(50, days=50),
            {},
            {"target_size": 5},
            lambda windows: len(windows) > 1,
            id="counted-from-one-page",
        ),
        pytest.param(
            datestamps(300, days=300), {}, {"max_windows": 4}, lambda windows: 1 < len(windows) <= 4, id="max-windows"
        ),
    ],
)
def test_windows_cover_the_records(app, source, stamps, source_options, limits, check):
    for option, value in source_options.items():
        setattr(source, option, value)
    source.extend(stamps)

    windows = _plan(**limits)

    assert check(windows)
    assert_windows_cover(windows, source)


def test_a_burst_ends_up_in_its_own_window(app, source, caplog):
    """Records imported at once must not make one window an order of magnitude slower than the rest."""
    source.granularity = DAY_GRANULARITY
    days = [(dt.date(2025, 1, 1) + dt.timedelta(days=offset)).isoformat() for offset in range(200)]
    burst_day = days[100]
    source.extend([day for day in days if day != burst_day] + [burst_day] * 500)

    windows = _plan()

    # the 500 records of the burst day can not be split (day granularity) - they get a window of
    # their own, the rest of the range is split into windows of a few records
    assert [w.start.date().isoformat() for w in windows].count(burst_day) == 1
    assert len(windows) > 10
    assert "can not be split further" in caplog.text
    assert_windows_cover(windows, source)


def test_no_windows_for_an_empty_source(app, source):
    assert _plan() == []
