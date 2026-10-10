"""RunState on the events file shared with robotframework-dashboard's JavaScript projection
(tests/javascript/live_projection.test.js there), so both projections stay in sync."""

import pytest

from conftest import DATA
from robotframework_events import RunState, from_dict, read_events
from robotframework_events.state import step_label

FIXTURE = DATA / "live_sample_events.jsonl"


@pytest.fixture(scope="module")
def events():
    return list(read_events(FIXTURE, strict=True))


@pytest.fixture
def state(events):
    return RunState.from_events(events)


def ev(type_, **fields):
    return from_dict({"v": 1, "seq": 0, "t": 100.0, "type": type_, **fields})


def test_ends_with_the_run_status_and_the_test_counts(state):
    assert state.status == "FAIL"
    assert state.counts() == {"PASS": 1, "FAIL": 1, "SKIP": 1, "RUNNING": 0, "done": 3, "total": 3, "pending": 0}
    assert state.running_step is None and state.running_test is None


def test_builds_the_tree_with_ids_from_the_events(state):
    assert state.root == "s1"
    assert state.nodes["s1"].children[:2] == ["s1-k1", "s1-t1"]  # suite setup, first test
    assert state.nodes["s1-t1"].children[0] == "s1-t1-k1"
    setup = state.nodes["s1-t1-k1"]
    assert (setup.kind, setup.name, setup.status) == ("SETUP", "Log", "PASS")
    assert [m.text for m in setup.messages] == ["test setup"]


def test_marks_the_failing_step_and_the_steps_that_did_not_run(state):
    failing = state.nodes["s1-t2-k2"]
    assert (failing.status, failing.message) == ("FAIL", "1 != 2")
    assert state.nodes["s1-t2-k3"].status == "NOT RUN"


def test_inherits_the_source_from_the_suite(state):
    assert state.nodes["s1-t1-k2-k1"].source.endswith("sample.robot")


def test_remembers_the_result_files(state):
    assert state.result_files["OUTPUT"].endswith("output.xml")


def test_tracks_the_deepest_running_step_and_falls_back_to_its_parent(events):
    upto = next(i for i, e in enumerate(events) if e.type == "step.started" and e.id == "s1-t1-k2-k2")
    state = RunState.from_events(events[: upto + 1])
    assert state.status == "RUNNING"
    assert state.running_test.id == "s1-t1"
    assert state.running_step.id == "s1-t1-k2-k2"
    assert [n.id for n in state.path("s1-t1-k2-k2")] == ["s1", "s1-t1", "s1-t1-k2", "s1-t1-k2-k2"]

    state.apply(ev("step.ended", id="s1-t1-k2-k2", status="PASS", elapsed=0.001))
    assert state.running_step.id == "s1-t1-k2"


def test_applies_status_changes_made_by_a_suite_teardown(state):
    state.apply(ev("status.changed", id="s1-t1", item="test", status="FAIL", message="Parent suite teardown failed"))
    test = state.nodes["s1-t1"]
    assert (test.status, test.message) == ("FAIL", "Parent suite teardown failed")


def test_starts_over_on_a_new_run(state):
    state.apply(ev("run.started", run="r2", rf="7.5"))
    assert state.nodes == {} and state.test_ids == []
    assert state.status == "RUNNING"


def test_step_labels(state):
    def find(kind):
        return next(n for n in state.nodes.values() if n.kind == kind)

    assert step_label(find("FOR")) == "${i}    IN RANGE    3"
    assert step_label(find("ITERATION")) == "${i} = 0"
    assert step_label(find("IF")) == "${i} == 1"
    assert step_label(find("VAR")) == "${x}"
    assert step_label(state.nodes["s1-t1-k1"]) == "Log"
