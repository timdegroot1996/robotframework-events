"""End-to-end: run a suite through robotcode's debugger and read `robotEvents` over DAP.

Uses the bundled robotcode next to this repository (``../robotcode/bundled/tool/robotcode``,
built with ``python scripts/package_local.py``; override with ``ROBOTCODE_LAUNCHER``).
Run with ``pytest -m e2e``.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from conftest import DATA, read_events

pytestmark = pytest.mark.e2e

LAUNCHER = Path(
    os.environ.get("ROBOTCODE_LAUNCHER", Path(__file__).parents[3] / "robotcode" / "bundled" / "tool" / "robotcode")
)


class DapClient:
    def __init__(self, port: int) -> None:
        deadline = time.monotonic() + 30
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port))
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
        self.file = self.sock.makefile("rb")
        self.seq = 0

    def request(self, command: str, arguments: dict[str, Any] | None = None) -> None:
        self.seq += 1
        body = json.dumps({"seq": self.seq, "type": "request", "command": command, "arguments": arguments or {}})
        data = body.encode()
        self.sock.sendall(b"Content-Length: %d\r\n\r\n" % len(data) + data)

    def read(self) -> dict[str, Any] | None:
        headers = {}
        while True:
            line = self.file.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                break
            key, value = line.decode().split(":", 1)
            headers[key.strip()] = value.strip()
        return json.loads(self.file.read(int(headers["Content-Length"])))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_debugger(tmp_path: Path, *flags: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str]:
    """Runs sample.robot through `robotcode debug`; returns the robotEvents batches, robotExited and the output."""
    port = free_port()
    debugger = subprocess.Popen(
        [
            sys.executable,
            str(LAUNCHER),
            "debug",
            "--tcp",
            str(port),
            "--wait-for-client",
            "--no-debug",
            *flags,
            "--",
            "--outputdir",
            str(tmp_path),
            "--console",
            "none",
            str(DATA / "sample.robot"),
        ],
        cwd=tmp_path,  # no robot.toml: only the flags decide
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    batches: list[dict[str, Any]] = []
    exited: dict[str, Any] | None = None
    try:
        client = DapClient(port)
        client.request("initialize", {"adapterID": "robotcode", "clientID": "e2e"})
        client.request("launch", {"noDebug": True})
        client.request("configurationDone")
        while (message := client.read()) is not None:
            if message.get("type") != "event":
                continue
            body = message.get("body")
            if isinstance(body, dict) and body.get("synced"):
                client.request("robot/sync")  # what the IDE does, robot waits for it
            if message["event"] == "robotEvents":
                batches.append(body)
            elif message["event"] == "robotExited":
                exited = body
            elif message["event"] == "terminated":
                break
    finally:
        output, _ = debugger.communicate(timeout=60)
    return batches, exited, output


@pytest.mark.skipif(not LAUNCHER.is_dir(), reason=f"robotcode launcher not found at {LAUNCHER}")
def test_events_arrive_in_complete_ordered_batches(tmp_path: Path) -> None:
    batches, exited, output = run_debugger(tmp_path, "--execution-events")

    assert exited is not None and exited["exitCode"] == 1
    assert "Traceback" not in output and "AssertionError" not in output, output

    events = [e for b in batches for e in b["events"]]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    for b in batches:
        assert b["run"] == events[0]["run"]
        assert (b["from"], b["to"]) == (b["events"][0]["seq"], b["events"][-1]["seq"])
    assert len(batches) < len(events)  # batched, not one message per event
    assert events[-1]["type"] == "run.ended"

    # the archive file holds exactly the streamed events
    assert read_events(tmp_path / "events.jsonl") == events


@pytest.mark.skipif(not LAUNCHER.is_dir(), reason=f"robotcode launcher not found at {LAUNCHER}")
def test_no_listener_unless_turned_on(tmp_path: Path) -> None:
    """Opt-in: without --execution-events (and without robot.toml) robotcode adds no listener at all."""
    batches, exited, _ = run_debugger(tmp_path)
    assert exited is not None and exited["exitCode"] == 1
    assert batches == []
    assert not list(tmp_path.glob("events*.jsonl"))
