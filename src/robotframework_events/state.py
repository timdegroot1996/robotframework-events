"""The state of a run, projected from its events: suites, tests and steps with status and messages.

The same projection runs in JavaScript in robotframework-dashboard's Live page. Both are tested
on a shared recorded events file, so they stay in sync.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .events import (
    Event,
    MessageLogged,
    ResultFileCreated,
    RunEnded,
    RunStarted,
    StatusChanged,
    StepEnded,
    StepScreenshot,
    StepStarted,
    SuiteEnded,
    SuiteStarted,
    TestEnded,
    TestStarted,
)

RUNNING = "RUNNING"


@dataclass(slots=True)
class Message:
    t: float
    level: str
    text: str
    html: bool = False


@dataclass(slots=True)
class Node:
    """A suite, test or step. ``kind`` is ``SUITE``, ``TEST`` or the step kind (``KEYWORD``, ``FOR``, ...)."""

    id: str
    kind: str
    parent: str | None
    started: SuiteStarted | TestStarted | StepStarted
    status: str = RUNNING
    message: str = ""
    start: float = 0.0
    end: float | None = None
    elapsed: float | None = None
    source: str | None = None
    children: list[str] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    screenshot: str | None = None  # the page after the step (listener option screenshots), relative to outputdir

    @property
    def name(self) -> str:
        return self.started.name or ""

    @property
    def lineno(self) -> int | None:
        return getattr(self.started, "lineno", None)


@dataclass(slots=True)
class RunState:
    """Apply events in order with :meth:`apply`, or build one with :meth:`from_events`.

    A ``run.started`` event starts over, so one state can follow a file that is rewritten
    by the next run.
    """

    run: RunStarted | None = None
    status: str | None = None  # None before the run starts, RUNNING, then the run status
    start: float | None = None
    end: float | None = None
    root: str | None = None
    total: int = 0  # tests in the run, known when the top-level suite starts
    nodes: dict[str, Node] = field(default_factory=dict)
    test_ids: list[str] = field(default_factory=list)
    result_files: dict[str, str] = field(default_factory=dict)
    running: list[str] = field(default_factory=list)  # ids of the open suites, tests and steps

    @classmethod
    def from_events(cls, events: Iterable[Event]) -> RunState:
        state = cls()
        for event in events:
            state.apply(event)
        return state

    def apply(self, event: Event) -> None:
        if isinstance(event, RunStarted):
            self._reset()
            self.run = event
            self.status = RUNNING
            self.start = event.t
        elif isinstance(event, SuiteStarted):
            if self.root is None:
                self.root = event.id
                self.total = event.tests
                self.start = self.start if self.start is not None else event.t
                self.status = self.status or RUNNING
            self._start(event, "SUITE", event.source)
        elif isinstance(event, TestStarted):
            self._start(event, "TEST", event.source)
            if event.id not in self.test_ids:
                self.test_ids.append(event.id)
        elif isinstance(event, StepStarted):
            self._start(event, event.kind, event.source)
        elif isinstance(event, (SuiteEnded, TestEnded, StepEnded)):
            node = self.nodes.get(event.id)
            if node is not None:
                node.status = event.status
                node.message = event.message or ""
                node.elapsed = event.elapsed
                node.end = event.t
            if event.id in self.running:
                del self.running[self.running.index(event.id) :]
        elif isinstance(event, MessageLogged):
            owner = self.nodes.get(event.parent or "")
            if owner is not None:
                owner.messages.append(Message(event.t, event.level, event.text or "", bool(event.html)))
        elif isinstance(event, StatusChanged):
            node = self.nodes.get(event.id)
            if node is not None:
                node.status = event.status
                node.message = event.message or ""
        elif isinstance(event, StepScreenshot):
            node = self.nodes.get(event.id)
            if node is not None:
                node.screenshot = event.path
        elif isinstance(event, ResultFileCreated):
            self.result_files[event.kind] = event.path
        elif isinstance(event, RunEnded):
            self.status = event.status
            self.end = event.t
            self.running.clear()

    def _reset(self) -> None:
        fresh = RunState()
        for name in self.__slots__:
            setattr(self, name, getattr(fresh, name))

    def _start(self, event: SuiteStarted | TestStarted | StepStarted, kind: str, source: str | None) -> None:
        parent = self.nodes.get(event.parent or "")
        node = Node(
            id=event.id,
            kind=kind,
            parent=event.parent,
            started=event,
            start=event.t,
            source=source if source is not None else (parent.source if parent else None),
        )
        self.nodes[event.id] = node
        if parent is not None:
            parent.children.append(event.id)
        self.running.append(event.id)

    # --- queries ----------------------------------------------------------------------

    @property
    def tests(self) -> list[Node]:
        return [self.nodes[i] for i in self.test_ids]

    @property
    def running_test(self) -> Node | None:
        return next((self.nodes[i] for i in reversed(self.running) if self.nodes[i].kind == "TEST"), None)

    @property
    def running_step(self) -> Node | None:
        """The deepest step that is running."""
        node = self.nodes[self.running[-1]] if self.running else None
        return node if node is not None and node.kind not in ("SUITE", "TEST") else None

    def counts(self) -> dict[str, int]:
        """Tests per status, plus ``done``, ``total`` and ``pending`` (not started yet)."""
        counts = {"PASS": 0, "FAIL": 0, "SKIP": 0, RUNNING: 0}
        for test in self.tests:
            counts[test.status] = counts.get(test.status, 0) + 1
        done = counts["PASS"] + counts["FAIL"] + counts["SKIP"]
        total = max(self.total, len(self.test_ids))
        return {**counts, "done": done, "total": total, "pending": max(0, total - done - counts[RUNNING])}

    def path(self, node_id: str) -> list[Node]:
        """The node and its ancestors, top-level suite first."""
        result = []
        node = self.nodes.get(node_id)
        while node is not None:
            result.append(node)
            node = self.nodes.get(node.parent or "")
        return result[::-1]


def step_label(node: Node) -> str:
    """What a step shows after its kind: the keyword name or the control structure's data."""
    event = node.started
    if not isinstance(event, StepStarted):
        return node.name
    kind = event.kind
    if kind == "FOR":
        variables = event.assign if isinstance(event.assign, list) else []
        return "    ".join(filter(None, [*variables, event.flavor or "", *(event.values or [])]))
    if kind == "ITERATION":
        values = event.assign if isinstance(event.assign, dict) else {}
        return "    ".join(f"{k} = {v}" for k, v in values.items())
    if kind in ("IF", "ELSE IF", "WHILE"):
        return event.condition or ""
    if kind == "EXCEPT":
        return "    ".join(event.patterns or [])
    if kind == "RETURN":
        return "    ".join(event.values or [])
    return event.name or ""
