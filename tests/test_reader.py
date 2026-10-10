"""read_events: plain and gzipped files, damaged lines, and following a file that is being written."""

import gzip
import threading
import time

import pytest

from conftest import DATA
from robotframework_events import read_events

FIXTURE = DATA / "live_sample_events.jsonl"
LINES = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)


def test_reads_plain_and_gzipped_files(tmp_path):
    gz = tmp_path / "events.jsonl.gz"
    with gzip.open(gz, "wt", encoding="utf-8") as file:
        file.writelines(LINES)
    plain = [e.to_dict() for e in read_events(FIXTURE)]
    assert len(plain) == len(LINES)
    assert [e.to_dict() for e in read_events(gz)] == plain


def test_skips_damaged_lines_unless_strict(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(LINES[0] + "{not json\n\n" + '{"v":1}\n' + LINES[1].rstrip("\n"), encoding="utf-8")
    assert [e.type for e in read_events(path)] == ["run.started", "suite.started"]
    with pytest.raises(ValueError, match="line 2"):
        list(read_events(path, strict=True))


def test_cannot_follow_gzipped_files(tmp_path):
    with pytest.raises(ValueError):
        list(read_events(tmp_path / "events.jsonl.gz", follow=True))


def write_slowly(path, chunks, delay=0.02, mode="a"):
    def run():
        for chunk in chunks:
            with open(path, mode, encoding="utf-8") as file:
                file.write(chunk)
            time.sleep(delay)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_follow_waits_for_the_file_and_stops_at_run_ended(tmp_path):
    path = tmp_path / "events.jsonl"
    # lines arrive in pieces, as from a buffered writer; the first only after a while
    text = "".join(LINES)
    chunks = [text[i : i + 700] for i in range(0, len(text), 700)]
    thread = write_slowly(path, chunks)
    events = list(read_events(path, follow=True, poll=0.01, timeout=10))
    thread.join()
    assert len(events) == len(LINES)
    assert events[-1].type == "run.ended"


def test_follow_gives_up_after_timeout(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("".join(LINES[:5]), encoding="utf-8")
    start = time.monotonic()
    assert len(list(read_events(path, follow=True, poll=0.01, timeout=0.2))) == 5
    assert time.monotonic() - start < 5


def test_follow_starts_again_when_the_file_is_rewritten(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("".join(LINES[:30]), encoding="utf-8")
    seen = []

    def rewrite():
        time.sleep(0.2)
        path.write_text(LINES[0], encoding="utf-8")  # the next run truncates the file
        time.sleep(0.2)
        with open(path, "a", encoding="utf-8") as file:
            file.writelines(LINES[1:])

    thread = threading.Thread(target=rewrite)
    thread.start()
    for event in read_events(path, follow=True, poll=0.01, timeout=10):
        seen.append(event.type)
    thread.join()
    assert seen.count("run.started") == 2
    assert seen[-1] == "run.ended"
