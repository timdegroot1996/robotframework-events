"""The rfevents command."""

from conftest import DATA, check_format, read_events, run_with_listener
from robotframework_events.cli import main

FIXTURE = DATA / "live_sample_events.jsonl"


def test_tail_shows_suites_tests_steps_failures_and_summary(capsys):
    assert main(["tail", str(FIXTURE), "--color", "never"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Sample"
    assert "    My Keyword    hello" in lines
    assert "      [WARN]  not one" in lines
    assert "  FAIL  Failing Test  (0.00 s)" in lines
    assert lines[-1] == "FAIL  Sample  3 tests, 1 passed, 1 failed, 1 skipped"


def test_tail_steps_and_level_options(capsys):
    main(["tail", str(FIXTURE), "--steps", "0", "--level", "FAIL", "--color", "never"])
    out = capsys.readouterr().out
    assert "My Keyword" not in out and "[WARN]" not in out
    assert "    [FAIL]  1 != 2" in out.splitlines()  # under its test

    main(["tail", str(FIXTURE), "--steps", "3", "--color", "never"])
    assert "        No Operation" in capsys.readouterr().out.splitlines()


def test_tail_colors(capsys):
    main(["tail", str(FIXTURE), "--color", "always"])
    assert "\033[31mFAIL\033[0m  Failing Test" in capsys.readouterr().out


def test_tail_missing_file_is_an_error(tmp_path, capsys):
    assert main(["tail", str(tmp_path / "missing.jsonl")]) == 2
    assert capsys.readouterr().err.startswith("rfevents: ")


def test_convert_writes_valid_events(tmp_path):
    _, output = run_with_listener(tmp_path, [DATA / "sample.robot"])
    converted = tmp_path / "converted.jsonl"
    assert main(["convert", str(output), "-o", str(converted)]) == 0
    events = read_events(converted)
    check_format(events)
    assert events[0]["type"] == "run.started" and events[-1]["type"] == "run.ended"
