"""Events built from an existing ``output.xml`` or ``output.json``.

Gives events for runs that were recorded without the listener, so they can be replayed.
What the result file does not store is left out: steps have no ``source`` and ``lineno``,
``run.started`` has no ``pid`` and ``cwd``, and children of ``robot:flatten`` keywords are
missing, as in ``log.html``. Statuses are final, so there are no ``status.changed`` events.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from robot.api import ExecutionResult
from robot.result import TestCase, TestSuite

from .events import FORMAT_VERSION
from .listener import ROOT_TYPES, _stats, step_fields

GENERATOR = re.compile(r"Robot (\S+) \(\w+ (\S+)")


def convert(path: str | os.PathLike[str], *, run: str | None = None, max_text: int = 4096) -> Iterator[dict[str, Any]]:
    """Yields the events of a result file as dicts, in the order a live run emits them."""
    result = ExecutionResult(str(path))
    return _Converter(max_text).events(result, str(path), run or str(uuid.uuid4()))


def _time(value: datetime | None) -> float | None:
    return round(value.timestamp(), 3) if value else None


class _Counter:
    __slots__ = ("children", "id")

    def __init__(self, id: str) -> None:
        self.id = id
        self.children = 0


class _Converter:
    def __init__(self, max_text: int) -> None:
        self.max_text = max_text
        self.seq = 0
        self.t = 0.0

    def emit(self, type_: str, t: float | None, **fields: Any) -> dict[str, Any]:
        self.seq += 1
        # NOT RUN items have no times; keep time moving forward
        self.t = max(self.t, t) if t is not None else self.t
        event: dict[str, Any] = {"v": FORMAT_VERSION, "seq": self.seq, "t": self.t, "type": type_}
        event.update((k, v) for k, v in fields.items() if v is not None and v != "")
        return event

    def events(self, result: Any, path: str, run: str) -> Iterator[dict[str, Any]]:
        suite = result.suite
        match = GENERATOR.match(getattr(result, "generator", "") or "")
        self.t = _time(suite.start_time) or 0.0
        yield self.emit(
            "run.started",
            self.t,
            run=run,
            outputdir=os.path.dirname(os.path.abspath(path)),
            rf=match.group(1) if match else "unknown",
            python=match.group(2) if match else None,
        )
        yield from self.suite(suite, "s1", None)
        yield self.emit("resultfile.created", None, kind="OUTPUT", path=path)
        yield self.emit("run.ended", None, status=suite.status, stats=_stats(suite))

    def suite(self, suite: TestSuite, id: str, parent: str | None) -> Iterator[dict[str, Any]]:
        yield self.emit(
            "suite.started",
            _time(suite.start_time),
            id=id,
            parent=parent,
            name=suite.name,
            longname=suite.full_name,
            source=str(suite.source) if suite.source else None,
            tests=suite.test_count,
        )
        counter = _Counter(id)
        if suite.has_setup:
            yield from self.step(suite.setup, counter, id)
        for index, child in enumerate(suite.suites, 1):
            yield from self.suite(child, f"{id}-s{index}", id)
        for index, test in enumerate(suite.tests, 1):
            yield from self.test(test, f"{id}-t{index}", id)
        if suite.has_teardown:
            yield from self.step(suite.teardown, counter, id)
        yield self.emit(
            "suite.ended",
            _time(suite.end_time),
            id=id,
            status=suite.status,
            message=suite.message,
            elapsed=round(suite.elapsed_time.total_seconds(), 3),
            stats=_stats(suite),
        )

    def test(self, test: TestCase, id: str, parent: str) -> Iterator[dict[str, Any]]:
        yield self.emit(
            "test.started",
            _time(test.start_time),
            id=id,
            parent=parent,
            name=test.name,
            longname=test.full_name,
            source=str(test.source) if test.source else None,
            lineno=test.lineno,
            tags=list(test.tags) or None,
        )
        counter = _Counter(id)
        if test.has_setup:
            yield from self.step(test.setup, counter, id)
        yield from self.body(test.body, counter, id)
        if test.has_teardown:
            yield from self.step(test.teardown, counter, id)
        yield self.emit(
            "test.ended",
            _time(test.end_time),
            id=id,
            status=test.status,
            message=test.message,
            elapsed=round(test.elapsed_time.total_seconds(), 3),
        )

    def body(self, items: Any, counter: _Counter, parent: str) -> Iterator[dict[str, Any]]:
        for item in items:
            if item.type == "MESSAGE":
                text = item.message or ""
                truncated = len(text) > self.max_text
                yield self.emit(
                    "message.logged",
                    _time(item.timestamp),
                    parent=parent,
                    level=item.level,
                    text=text[: self.max_text] if truncated else text,
                    truncated=True if truncated else None,
                    html=True if item.html else None,
                )
            elif item.type in ROOT_TYPES:
                # IF/TRY branches are numbered as children of the root's parent
                yield from self.body(item.body, counter, parent)
            else:
                yield from self.step(item, counter, parent)

    def step(self, item: Any, counter: _Counter, parent: str) -> Iterator[dict[str, Any]]:
        counter.children += 1
        id = f"{counter.id}-k{counter.children}"
        kind = item.type
        yield self.emit(
            "step.started", _time(item.start_time), id=id, parent=parent, kind=kind, **step_fields(kind, item)
        )
        own = _Counter(id)
        if getattr(item, "has_setup", False):
            yield from self.step(item.setup, own, id)
        if hasattr(item, "body"):
            yield from self.body(item.body, own, id)
        if getattr(item, "has_teardown", False):
            yield from self.step(item.teardown, own, id)
        yield self.emit(
            "step.ended",
            _time(item.end_time),
            id=id,
            status=item.status,
            message=item.message,
            elapsed=round(item.elapsed_time.total_seconds(), 4),
        )
