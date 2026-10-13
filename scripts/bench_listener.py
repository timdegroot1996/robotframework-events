"""Listener overhead benchmarks, see docs/performance.md.

    python scripts/bench_listener.py run [--rounds 5] [--n 4000] [--listener path.py]   # full runs
    python scripts/bench_listener.py micro [--repeat 20]           # step events alone, replayed from a real run

``run`` alternates plain and listened runs of tests/data/loop.robot and prints the best of each and
the ratio. ``micro`` records the (data, result) pairs of every body item of one run, then replays
``start_body_item`` / ``end_body_item`` on a fresh listener writing to a file, and prints microseconds
per event, so one change to the step path can be measured without Robot Framework around it.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from robot import run  # noqa: E402

from robotframework_events import listener as rfe  # noqa: E402

LOOP = ROOT / "tests" / "data" / "loop.robot"


def _run(n: int, **options) -> float:
    start = time.perf_counter()
    run(str(LOOP), variable=[f"N:{n}"], output="NONE", log="NONE", report="NONE", console="none", **options)
    return time.perf_counter() - start


def bench_run(rounds: int, n: int, listener: str | None) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        listener = listener or f"robotframework_events.Listener;file={Path(tmp) / 'events.jsonl'}"
        _run(n // 10)
        _run(n // 10, listener=listener)  # warm up imports
        plain, listened = [], []
        for _ in range(rounds):
            plain.append(_run(n))
            listened.append(_run(n, listener=listener))
    best_plain, best_listened = min(plain), min(listened)
    events = 2 * (2 * n + 1)
    print(
        f"python {sys.version.split()[0]}, {2 * n + 1} body items: plain {best_plain:.3f}s, "
        f"listener {best_listened:.3f}s, ratio {best_listened / best_plain:.3f} "
        f"(median {statistics.median(listened) / statistics.median(plain):.3f}), "
        f"{(best_listened - best_plain) / events * 1e6:.2f} us/event"
    )


class _Recorder:
    ROBOT_LISTENER_API_VERSION = 3

    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object]] = []

    def start_body_item(self, data, result) -> None:
        self.calls.append(("start", data, result))

    def end_body_item(self, data, result) -> None:
        self.calls.append(("end", data, result))


def bench_micro(repeat: int, n: int) -> None:
    recorder = _Recorder()
    run(str(LOOP), variable=[f"N:{n}"], output="NONE", log="NONE", report="NONE", console="none", listener=recorder)
    calls = recorder.calls
    with tempfile.TemporaryDirectory() as tmp:
        times = []
        for _ in range(repeat):
            listener = rfe.Listener(file=os.path.join(tmp, "events.jsonl"), flush="0")
            listener._out = open(os.path.join(tmp, "events.jsonl"), "wb", buffering=1 << 16)  # noqa: SIM115
            listener._stack.append(rfe._Frame("s1", str(LOOP), None))
            listener._stack.append(rfe._Frame("s1-t1", str(LOOP), listener._stack[-1]))
            start_item, end_item = listener.start_body_item, listener.end_body_item
            start = time.perf_counter()
            for what, data, result in calls:
                if what == "start":
                    start_item(data, result)
                else:
                    end_item(data, result)
            times.append(time.perf_counter() - start)
            listener._out.close()
    best = min(times)
    print(
        f"python {sys.version.split()[0]}, {len(calls)} events: best {best * 1e3:.1f} ms, "
        f"{best / len(calls) * 1e6:.2f} us/event (median {statistics.median(times) / len(calls) * 1e6:.2f})"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("what", choices=("run", "micro"))
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--repeat", type=int, default=20)
    parser.add_argument("--n", type=int, default=4000)
    parser.add_argument("--listener", help="run: another listener to compare, e.g. an empty one")
    args = parser.parse_args()
    if args.what == "run":
        bench_run(args.rounds, args.n, args.listener)
    else:
        bench_micro(args.repeat, args.n)


if __name__ == "__main__":
    main()
