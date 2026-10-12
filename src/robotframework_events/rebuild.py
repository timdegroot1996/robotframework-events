"""An ``output.xml`` built from events, for runs that ended without one.

A run that crashed or was killed leaves no ``output.xml``, but its events file has every suite,
test, step and message up to the moment it stopped. :func:`rebuild` turns those events into a
Robot Framework result, so the run can still go to a history (robotframework-dashboard) or into
``rebot``. What did not finish is failed with :data:`NOT_FINISHED`; tests that never started
are left out.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from robot.result import Result, TestSuite

from .events import Event, StepStarted, TestStarted
from .state import RUNNING, Node, RunState

NOT_FINISHED = "Not finished: the run stopped before this ended."
"""The message of tests and steps that were still running when the run stopped."""

RUN_NOT_FINISHED = "The run did not finish. This result is rebuilt from its execution events."
"""The message of the top-level suite of a run that did not end."""


def rebuild(events: Iterable[Event]) -> Result:
    """The result of a run, built from its events (the last run when there are several)."""
    state = RunState.from_events(events)
    if state.root is None:
        raise ValueError("no suite in the events")
    end = state.end if state.end is not None else _last_time(state)
    builder = _Builder(state, end)
    suite = builder.suite(state.nodes[state.root])
    if state.status == RUNNING:
        suite.message = RUN_NOT_FINISHED
    result = Result()  # the argument for the suite was renamed after Robot Framework 7.0
    result.suite = suite
    if state.run is not None:
        result.generator = f"Robot {state.run.rf} (rebuilt by robotframework-events)"
    return result


def write_rebuilt(events: Iterable[Event], path: str | os.PathLike[str]) -> None:
    """Writes the result :func:`rebuild` builds to ``path`` as ``output.xml``."""
    rebuild(events).save(os.fspath(path))  # type: ignore[no-untyped-call]


def _last_time(state: RunState) -> float:
    times = [node.end if node.end is not None else node.start for node in state.nodes.values()]
    times += [message.t for node in state.nodes.values() for message in node.messages]
    return max(times, default=state.start or 0.0)


def _time(t: float) -> datetime:
    return datetime.fromtimestamp(t)


class _Builder:
    def __init__(self, state: RunState, end: float) -> None:
        self.state = state
        self.end = end

    def times(self, node: Node) -> dict[str, Any]:
        """Status, message and times of a node; one that is still running fails at the end of the run."""
        if node.status == RUNNING:
            status, message, elapsed = "FAIL", NOT_FINISHED, self.end - node.start
        else:
            status, message = node.status, node.message
            elapsed = node.elapsed if node.elapsed is not None else (node.end or node.start) - node.start
        return {
            "status": status,
            "message": message,
            "start_time": _time(node.start),
            "elapsed_time": timedelta(seconds=max(0.0, elapsed)),
        }

    def children(self, node: Node) -> list[Node]:
        return [self.state.nodes[i] for i in node.children]

    def suite(self, node: Node) -> TestSuite:
        times = self.times(node)
        suite = TestSuite(
            name=node.name,
            source=node.started.source if node.started.source else None,
            start_time=times["start_time"],
            elapsed_time=times["elapsed_time"],
        )
        if node.message:
            suite.message = node.message
        for child in self.children(node):
            if child.kind == "SUITE":
                suite.suites.append(self.suite(child))
            elif child.kind == "TEST":
                self.test(suite, child)
            else:
                self.step(suite, child)
        return suite

    def test(self, suite: TestSuite, node: Node) -> None:
        started = node.started
        assert isinstance(started, TestStarted)
        test = suite.tests.create(name=node.name, lineno=started.lineno, tags=started.tags or (), **self.times(node))
        for child in self.children(node):
            self.step(test, child)

    def step(self, parent: Any, node: Node) -> None:
        started = node.started
        assert isinstance(started, StepStarted)
        item = self.create(parent, node.kind, started, self.times(node))
        for message in node.messages:
            try:
                item.body.create_message(message.text, message.level, message.html, _time(message.t))
            except (AttributeError, TypeError):
                break  # a body without messages
        for child in self.children(node):
            self.step(item, child)

    def create(self, parent: Any, kind: str, e: StepStarted, times: dict[str, Any]) -> Any:
        # suites, tests and keywords have their own setup and teardown
        if kind in ("SETUP", "TEARDOWN") and hasattr(parent, "setup"):
            fixture = parent.setup if kind == "SETUP" else parent.teardown
            return fixture.config(name=e.name, owner=e.owner, args=e.args or (), type=kind, **times)
        body = parent.body
        assign = e.assign if isinstance(e.assign, list) else ()
        if kind == "KEYWORD":
            return body.create_keyword(name=e.name, owner=e.owner, args=e.args or (), assign=assign, **times)
        if kind == "FOR":
            return body.create_for(assign=assign, flavor=e.flavor or "IN", values=e.values or (), **times)
        if kind == "ITERATION":
            if isinstance(e.assign, dict):
                return body.create_iteration(assign=e.assign, **times)
            return body.create_iteration(**times)
        if kind == "WHILE":
            return body.create_while(condition=e.condition, limit=e.limit, **times)
        if kind in ("IF", "ELSE IF", "ELSE", "TRY", "EXCEPT", "FINALLY"):
            return self.branch(body, kind, e, times)
        if kind == "GROUP" and hasattr(body, "create_group"):
            return body.create_group(name=e.name or "", **times)
        if kind == "VAR":
            return body.create_var(name=e.name or "", value=e.values or (), scope=e.scope, **times)
        if kind == "RETURN":
            return body.create_return(values=e.values or (), **times)
        if kind == "BREAK":
            return body.create_break(**times)
        if kind == "CONTINUE":
            return body.create_continue(**times)
        if kind == "ERROR":
            return body.create_error(values=e.values or (), **times)
        # a kind this Robot Framework version does not have (GROUP before 7.2)
        return body.create_keyword(name=" ".join(filter(None, [kind, e.name])), **times)

    def branch(self, body: Any, kind: str, e: StepStarted, times: dict[str, Any]) -> Any:
        """IF and TRY branches; the events have no IF/ELSE or TRY/EXCEPT root, the branches follow each other."""
        last = body[-1] if len(body) else None
        if kind == "IF" or (kind == "ELSE IF" and getattr(last, "type", None) != "IF/ELSE ROOT"):
            root = body.create_if(status=times["status"], start_time=times["start_time"])
        elif kind == "TRY":
            root = body.create_try(status=times["status"], start_time=times["start_time"])
        elif last is not None and getattr(last, "type", None) in ("IF/ELSE ROOT", "TRY/EXCEPT ROOT"):
            root = last
        else:
            root = body.create_if(status=times["status"], start_time=times["start_time"])
        if root.type == "IF/ELSE ROOT":
            branch = root.body.create_branch(type=kind, condition=e.condition, **times)
        else:
            patterns = e.patterns or ()
            assign = e.assign if isinstance(e.assign, str) else None
            branch = root.body.create_branch(type=kind, patterns=patterns, assign=assign, **times)
        # the root runs as long as its branches
        root.elapsed_time = branch.end_time - root.start_time
        root.status = _root_status(root)
        return branch


def _root_status(root: Any) -> str:
    """An IF root fails with a failed branch; a TRY root also passes when an EXCEPT caught its failure."""
    branches = [(branch.type, branch.status) for branch in root.body]
    ran = [status for _, status in branches if status != "NOT RUN"]
    if not ran:
        return "NOT RUN"
    caught = any(kind == "EXCEPT" and status != "NOT RUN" for kind, status in branches)
    failed = any(status == "FAIL" and not (kind == "TRY" and caught) for kind, status in branches)
    if failed:
        return "FAIL"
    return "SKIP" if "SKIP" in ran else "PASS"
