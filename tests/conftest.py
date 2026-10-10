import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from robot import run

from robotframework_events import from_dict, schema

HERE = Path(__file__).parent
DATA = HERE / "data"
VALIDATOR = Draft202012Validator(schema(), format_checker=Draft202012Validator.FORMAT_CHECKER)


def read_events(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def check_format(events: list[dict[str, Any]]) -> None:
    """Every event matches the JSON Schema and survives a round trip through the typed classes."""
    for event in events:
        VALIDATOR.validate(event)
        assert from_dict(event).to_dict() == event


def run_with_listener(
    tmp_path: Path, sources: Sequence[Path], listener_args: str = "", **options: Any
) -> tuple[list[dict[str, Any]], Path]:
    """Runs Robot Framework with the listener; returns the events (checked with :func:`check_format`)
    and the output.xml path."""
    events_file = tmp_path / "events.jsonl"
    # ';' separates listener arguments so Windows drive letters survive
    listener = f"robotframework_events.Listener;file={events_file}" + (f";{listener_args}" if listener_args else "")
    options.setdefault("console", "none")
    options.setdefault("log", "NONE")
    options.setdefault("report", "NONE")
    run(*[str(s) for s in sources], listener=listener, outputdir=str(tmp_path), stdout=None, stderr=None, **options)
    events = read_events(events_file)
    check_format(events)
    return events, tmp_path / "output.xml"


@pytest.fixture
def sample_events(tmp_path: Path) -> list[dict[str, Any]]:
    events, _ = run_with_listener(tmp_path, [DATA / "sample.robot"])
    return events
