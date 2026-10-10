"""Event format and listener options, on tests/data/sample.robot."""

from pathlib import Path

import pytest

import robotframework_events
from conftest import DATA, check_format, read_events, run_with_listener

REQUIRED = {"v", "seq", "t", "type"}


def by_type(events, type_):
    return [e for e in events if e["type"] == type_]


def test_every_event_has_envelope_fields_and_gapless_seq(sample_events):
    assert all(e.keys() >= REQUIRED for e in sample_events)
    assert [e["seq"] for e in sample_events] == list(range(1, len(sample_events) + 1))
    assert all(e["v"] == 1 for e in sample_events)


def test_run_events_frame_the_stream(sample_events):
    assert sample_events[0]["type"] == "run.started"
    assert sample_events[0]["run"]
    assert sample_events[-1]["type"] == "run.ended"
    assert sample_events[-1]["stats"] == {"total": 3, "passed": 1, "failed": 1, "skipped": 1}


def test_starts_and_ends_are_balanced_and_nested(sample_events):
    stack = []
    for e in sample_events:
        kind, _, phase = e["type"].partition(".")
        if phase == "started" and kind in ("suite", "test", "step"):
            stack.append(e["id"])
        elif phase == "ended" and kind in ("suite", "test", "step"):
            assert stack.pop() == e["id"]
    assert stack == []


def test_parent_is_the_enclosing_open_item(sample_events):
    stack = []
    for e in sample_events:
        if e["type"] in ("suite.started", "test.started", "step.started"):
            assert e.get("parent") == (stack[-1] if stack else None)
            stack.append(e["id"])
        elif e["type"] in ("suite.ended", "test.ended", "step.ended"):
            stack.pop()
        elif e["type"] == "message.logged":
            assert e["parent"] == stack[-1]


def test_if_and_try_roots_are_not_emitted(sample_events):
    kinds = {e["kind"] for e in by_type(sample_events, "step.started")}
    assert "IF/ELSE ROOT" not in kinds and "TRY/EXCEPT ROOT" not in kinds
    assert {"IF", "ELSE", "TRY", "EXCEPT", "FOR", "ITERATION", "GROUP", "VAR"} <= kinds


def test_keyword_fields(sample_events):
    log = next(e for e in by_type(sample_events, "step.started") if e.get("args") == ["hello"])
    assert log["name"] == "My Keyword" and log["kind"] == "KEYWORD" and log["lineno"] == 8
    builtin = next(e for e in by_type(sample_events, "step.started") if e.get("owner") == "BuiltIn")
    assert builtin["name"] == "Log"


def test_control_structure_fields(sample_events):
    steps = by_type(sample_events, "step.started")
    loop = next(e for e in steps if e["kind"] == "FOR")
    assert loop["assign"] == ["${i}"] and loop["flavor"] == "IN RANGE" and loop["values"] == ["3"]
    iteration = next(e for e in steps if e["kind"] == "ITERATION")
    assert iteration["assign"] == {"${i}": "0"}
    branch = next(e for e in steps if e["kind"] == "IF")
    assert branch["condition"] == "${i} == 1"


def test_source_is_inherited_from_parent(sample_events):
    steps = by_type(sample_events, "step.started")
    # steps written in the suite file inherit its source; nothing repeats it
    assert all("source" not in e for e in steps)


def test_messages_carry_level_and_text(sample_events):
    warn = next(e for e in by_type(sample_events, "message.logged") if e["level"] == "WARN")
    assert warn["text"] == "not one"


def test_failure_and_not_run_status(sample_events):
    ended = {e["id"]: e for e in by_type(sample_events, "step.ended")}
    assert ended["s1-t2-k2"]["status"] == "FAIL" and ended["s1-t2-k2"]["message"] == "1 != 2"
    assert ended["s1-t2-k3"]["status"] == "NOT RUN"


def test_result_files_are_reported(tmp_path: Path):
    events, output = run_with_listener(tmp_path, [DATA / "sample.robot"], log="log.html")
    files = {e["kind"]: e["path"] for e in by_type(events, "resultfile.created")}
    assert Path(files["OUTPUT"]) == output and "LOG" in files


def test_option_structures_off_keeps_ids_and_reparents(tmp_path: Path):
    events, _ = run_with_listener(tmp_path, [DATA / "sample.robot"], "structures=false")
    steps = by_type(events, "step.started")
    assert {e["kind"] for e in steps} <= {"KEYWORD", "SETUP", "TEARDOWN"}
    passed = {e["id"] for e in by_type(events, "step.ended") if e["status"] == "PASS"}
    log_one = next(e for e in steps if e.get("args") == ["one"] and e["id"] in passed)
    assert log_one["id"] == "s1-t1-k3-k2-k1-k1"  # FOR > ITERATION > IF branch > Log
    assert log_one["parent"] == "s1-t1"


def test_option_messages_off_and_level(tmp_path: Path):
    events, _ = run_with_listener(tmp_path / "a", [DATA / "sample.robot"], "messages=false")
    assert not by_type(events, "message.logged")
    events, _ = run_with_listener(tmp_path / "b", [DATA / "sample.robot"], "level=WARN")
    assert {e["level"] for e in by_type(events, "message.logged")} == {"WARN", "FAIL"}


def test_option_args_off(tmp_path: Path):
    events, _ = run_with_listener(tmp_path, [DATA / "sample.robot"], "args=false")
    assert all("args" not in e for e in by_type(events, "step.started"))


def test_long_message_is_truncated(tmp_path: Path):
    suite = tmp_path / "long.robot"
    suite.write_text("*** Test Cases ***\nLong\n    Log    ${{'x' * 50}}\n", encoding="utf-8")
    events, _ = run_with_listener(tmp_path, [suite], "max_text=10")
    message = by_type(events, "message.logged")[0]
    assert message["text"] == "x" * 10 and message["truncated"] is True


def test_callbacks_receive_the_same_events_and_file_none(tmp_path: Path):
    received = []
    robotframework_events.add_callback(received.append)
    try:
        from robot import run

        run(
            str(DATA / "sample.robot"),
            listener="robotframework_events.Listener;file=NONE",
            outputdir=str(tmp_path),
            console="none",
            log="NONE",
            report="NONE",
        )
    finally:
        robotframework_events.remove_callback(received.append)
    assert received[0]["type"] == "run.started" and received[-1]["type"] == "run.ended"
    check_format(received)
    assert not (tmp_path / "events.jsonl").exists()


def test_failing_callback_is_removed_and_run_continues(tmp_path: Path):
    def broken(event):
        raise RuntimeError("boom")

    robotframework_events.add_callback(broken)
    events, _ = run_with_listener(tmp_path, [DATA / "sample.robot"])
    assert broken not in robotframework_events.listener._callbacks
    assert events[-1]["type"] == "run.ended"


def test_default_file_is_in_output_dir(tmp_path: Path):
    from robot import run

    run(
        str(DATA / "sample.robot"),
        listener="robotframework_events.Listener",
        outputdir=str(tmp_path),
        console="none",
        log="NONE",
        report="NONE",
    )
    events = read_events(tmp_path / "events.jsonl")
    assert events[-1]["type"] == "run.ended"
    check_format(events)


def test_flattened_keyword_is_marked_and_children_still_emitted(tmp_path: Path):
    suite = tmp_path / "flat.robot"
    suite.write_text(
        "*** Test Cases ***\nT\n    Flat\n\n*** Keywords ***\nFlat\n    [Tags]    robot:flatten\n    Log    inner\n",
        encoding="utf-8",
    )
    events, _ = run_with_listener(tmp_path, [suite])
    steps = {e["id"]: e for e in by_type(events, "step.started")}
    assert steps["s1-t1-k1"]["flatten"] is True
    assert steps["s1-t1-k1-k1"]["args"] == ["inner"]


def test_old_robot_framework_is_refused():
    from robotframework_events.listener import _check_robot_version

    for version in ("7.5", "7.5.1", "7.6rc1", "8.0"):
        _check_robot_version(version)
    for version in ("7.4.2", "6.1"):
        with pytest.raises(RuntimeError, match=r"requires Robot Framework 7\.5"):
            _check_robot_version(version)
