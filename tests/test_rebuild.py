"""output.xml rebuilt from events, for runs that ended without one."""

from typing import Any

from robot.api import ExecutionResult

from conftest import DATA, run_with_listener
from robotframework_events import from_dict, rebuild
from robotframework_events.cli import main
from robotframework_events.rebuild import NOT_FINISHED, RUN_NOT_FINISHED


def tree(item: Any) -> list[tuple[Any, ...]]:
    """Suites, tests, steps and messages of a result, in order, with what the events keep of them."""
    if hasattr(item, "suites"):
        lines: list[tuple[Any, ...]] = [("SUITE", item.name, item.status)]
        children = [item.setup, *item.suites, *item.tests, item.teardown]
    else:
        kind = getattr(item, "type", "TEST")  # tests have no type before Robot Framework 7.1
        name = getattr(item, "name", None) if kind in ("KEYWORD", "SETUP", "TEARDOWN", "TEST") else None
        lines = [(kind, name, item.status, item.message if kind == "TEST" else None)]
        children = [getattr(item, "setup", None), *item.body, getattr(item, "teardown", None)]
    for child in children:
        kind = getattr(child, "type", "TEST") if child is not None else None
        if child is None or (kind in ("SETUP", "TEARDOWN") and not child):
            continue
        if kind == "MESSAGE":
            lines.append(("MESSAGE", child.level, child.message, child.html))
        else:
            lines.extend(tree(child))
    return lines


def test_rebuilt_output_has_the_run_of_a_complete_run(tmp_path):
    _, output = run_with_listener(tmp_path, [DATA / "sample.robot"])
    rebuilt = tmp_path / "rebuilt.xml"
    assert main(["rebuild", str(tmp_path / "events.jsonl"), "-o", str(rebuilt)]) == 0
    original = ExecutionResult(str(output)).suite
    result = ExecutionResult(str(rebuilt)).suite
    assert tree(result) == tree(original)
    stats = result.statistics
    assert (stats.passed, stats.failed, stats.skipped) == (1, 1, 1)
    assert result.message == ""


def test_what_did_not_finish_fails(tmp_path):
    events, _ = run_with_listener(tmp_path, [DATA / "sample.robot"])
    # the run stops in the middle of the second test's first keyword
    test = next(e for e in events if e["type"] == "test.started" and e["name"] == "Failing Test")
    step = next(e for e in events if e["type"] == "step.started" and e.get("parent") == test["id"])
    cut = events[: events.index(step) + 1]
    suite = rebuild(from_dict(e) for e in cut).suite
    assert suite.message == RUN_NOT_FINISHED
    assert [(t.name, t.status) for t in suite.tests] == [("Passing With Structures", "PASS"), ("Failing Test", "FAIL")]
    failing = suite.tests[1]
    assert failing.message == NOT_FINISHED
    assert (failing.body[0].name, failing.body[0].status, failing.body[0].message) == (
        "My Keyword",
        "FAIL",
        NOT_FINISHED,
    )
    assert suite.status == "FAIL"
    # suite teardown never ran
    assert not suite.teardown
