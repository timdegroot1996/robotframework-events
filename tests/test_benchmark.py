"""Overhead on the no-op loop, the worst case. Run with ``pytest -m bench``.

Measured 2026-10-14 (RF 7.5, Windows, best of 5 alternating runs, three rounds, see
``scripts/bench_listener.py``): Python 3.11-3.14 11-19%, 3.10 18-26% (27-35% before step
events were written without an event dict, 2026-10-13). An empty listener alone costs 4-7%.
Single runs vary by about 7 points, so the budget below is a regression guard.
"""

import sys
import time
from pathlib import Path

import pytest
from robot import run

from conftest import DATA

pytestmark = pytest.mark.bench

N = 4000
# Python 3.10 runs Robot Framework faster but the listener slower, so its ratio is higher
BUDGET = 1.30 if sys.version_info < (3, 11) else 1.25


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
