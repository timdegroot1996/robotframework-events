"""Overhead on the no-op loop, the worst case. Run with ``pytest -m bench``.

The plan aims for 25%. Measured 2026-10-10 (RF 7.5, Python 3.14, Windows, best of 15
alternating runs, two rounds): an empty listener costs 5%, a minimal id-tracking listener 22%,
this listener 27-28%, about 16-17 us per event (32-34% and 19-21 us before step events were
built without empty fields and written from templates). Single runs vary by about 7 points,
so the budget below is a regression guard.
"""

import time
from pathlib import Path

import pytest
from robot import run

from conftest import DATA

pytestmark = pytest.mark.bench

N = 4000
BUDGET = 1.35


def best_of(runs: int, **options) -> float:
    best = float("inf")
    for _ in range(runs):
        start = time.perf_counter()
        run(
            str(DATA / "loop.robot"),
            variable=[f"N:{N}"],
            output="NONE",
            log="NONE",
            report="NONE",
            console="none",
            **options,
        )
        best = min(best, time.perf_counter() - start)
    return best


def test_listener_overhead_within_budget(tmp_path: Path):
    plain = best_of(3)
    listened = best_of(3, listener=f"robotframework_events.Listener;file={tmp_path / 'events.jsonl'}")
    ratio = listened / plain
    print(f"\n{2 * N} body items: no listener {plain:.2f}s, listener {listened:.2f}s, ratio {ratio:.2f}")
    assert ratio <= BUDGET
