"""Typed events of format v1, and the JSON Schema that describes one line of an events file.

The listener emits plain dicts, which is faster; these classes are for programs that read
events. :func:`from_dict` turns a decoded line into an event, :meth:`Event.to_dict` turns it
back. Unknown fields are ignored and unknown event types become :class:`UnknownEvent`, so
readers keep working when newer writers add to the format.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, fields
from importlib import resources
from typing import Any, ClassVar

FORMAT_VERSION = 1
SCHEMA_FILE = "events-v1.schema.json"

Stats = dict[str, int]
"""``{"total": n, "passed": n, "failed": n, "skipped": n}``"""


@dataclass(slots=True, kw_only=True)
class Event:
    """Fields that every event has. ``type`` is the class attribute ``TYPE``."""

    TYPE: ClassVar[str] = ""

    v: int = FORMAT_VERSION
    seq: int
    t: float

    @property
    def type(self) -> str:
        return self.TYPE

    def to_dict(self) -> dict[str, Any]:
        """The event as written to a file: envelope first, fields that are None left out."""
        data: dict[str, Any] = {"v": self.v, "seq": self.seq, "t": self.t, "type": self.type}
        for f in fields(self):
            if f.name not in _ENVELOPE:
                value = getattr(self, f.name)
                if value is not None:
                    data[f.name] = value
        return data


@dataclass(slots=True, kw_only=True)
class RunStarted(Event):
    """``python``, ``pid`` and ``cwd`` are missing in events converted from a result file."""

    TYPE: ClassVar[str] = "run.started"

    run: str
    rf: str
    python: str | None = None
    pid: int | None = None
    cwd: str | None = None


@dataclass(slots=True, kw_only=True)
class RunEnded(Event):
    TYPE: ClassVar[str] = "run.ended"

    status: str
    stats: Stats


@dataclass(slots=True, kw_only=True)
class SuiteStarted(Event):
    TYPE: ClassVar[str] = "suite.started"

    id: str
    parent: str | None = None
    name: str
    longname: str
    source: str | None = None
    tests: int


@dataclass(slots=True, kw_only=True)
class SuiteEnded(Event):
    TYPE: ClassVar[str] = "suite.ended"

    id: str
    status: str
    message: str | None = None
    elapsed: float
    stats: Stats


@dataclass(slots=True, kw_only=True)
class TestStarted(Event):
    TYPE: ClassVar[str] = "test.started"
    __test__: ClassVar[bool] = False  # not a pytest test class

    id: str
    parent: str
    name: str
    longname: str
    source: str | None = None
    lineno: int | None = None
    tags: list[str] | None = None


@dataclass(slots=True, kw_only=True)
class TestEnded(Event):
    TYPE: ClassVar[str] = "test.ended"
    __test__: ClassVar[bool] = False

    id: str
    status: str
    message: str | None = None
    elapsed: float


@dataclass(slots=True, kw_only=True)
class StepStarted(Event):
    """A keyword, setup, teardown or control structure. Which fields are set depends on ``kind``.

    ``source`` is left out when it equals the parent's source. ``assign`` is a list of variables
    for keywords and FOR, a ``{variable: value}`` dict for ITERATION and a string for EXCEPT.
    """

    TYPE: ClassVar[str] = "step.started"

    id: str
    parent: str | None = None
    kind: str
    source: str | None = None
    lineno: int | None = None
    name: str | None = None
    owner: str | None = None
    args: list[str] | None = None
    assign: list[str] | dict[str, str] | str | None = None
    flatten: bool | None = None
    flavor: str | None = None
    values: list[str] | None = None
    condition: str | None = None
    limit: str | None = None
    patterns: list[str] | None = None
    scope: str | None = None


@dataclass(slots=True, kw_only=True)
class StepEnded(Event):
    TYPE: ClassVar[str] = "step.ended"

    id: str
    status: str
    message: str | None = None
    elapsed: float


@dataclass(slots=True, kw_only=True)
class MessageLogged(Event):
    TYPE: ClassVar[str] = "message.logged"

    parent: str | None = None
    level: str
    text: str | None = None
    truncated: bool | None = None
    html: bool | None = None


@dataclass(slots=True, kw_only=True)
class StatusChanged(Event):
    """A suite teardown changed the status of a suite or test that already ended."""

    TYPE: ClassVar[str] = "status.changed"

    id: str
    item: str
    status: str
    message: str | None = None


@dataclass(slots=True, kw_only=True)
class ResultFileCreated(Event):
    TYPE: ClassVar[str] = "resultfile.created"

    kind: str
    path: str


@dataclass(slots=True, kw_only=True)
class UnknownEvent(Event):
    """An event type this version does not know. ``data`` holds the fields besides the envelope."""

    name: str
    data: dict[str, Any]

    @property
    def type(self) -> str:
        return self.name

    def to_dict(self) -> dict[str, Any]:
        return {"v": self.v, "seq": self.seq, "t": self.t, "type": self.name, **self.data}


EVENT_CLASSES: dict[str, type[Event]] = {
    cls.TYPE: cls
    for cls in (
        RunStarted,
        SuiteStarted,
        TestStarted,
        StepStarted,
        MessageLogged,
        StepEnded,
        TestEnded,
        SuiteEnded,
        StatusChanged,
        ResultFileCreated,
        RunEnded,
    )
}

_ENVELOPE = frozenset({"v", "seq", "t", "type"})
_FIELDS = {type_: frozenset(f.name for f in fields(cls)) - _ENVELOPE for type_, cls in EVENT_CLASSES.items()}


def from_dict(data: Mapping[str, Any]) -> Event:
    """Builds the typed event for one decoded line.

    Unknown fields are ignored; an unknown ``type`` gives an :class:`UnknownEvent`.
    Raises ``ValueError`` when an envelope field or a required field is missing.
    """
    try:
        envelope = {"v": data["v"], "seq": data["seq"], "t": data["t"]}
        type_ = data["type"]
    except KeyError as e:
        raise ValueError(f"event without {e.args[0]!r}: {dict(data)}") from None
    cls = EVENT_CLASSES.get(type_)
    if cls is None:
        return UnknownEvent(**envelope, name=type_, data={k: v for k, v in data.items() if k not in _ENVELOPE})
    known = _FIELDS[type_]
    try:
        return cls(**envelope, **{k: v for k, v in data.items() if k in known})
    except TypeError as e:
        raise ValueError(f"invalid {type_} event: {e}") from None


def schema() -> dict[str, Any]:
    """The JSON Schema (draft 2020-12) for one line of an events file, format v1. Returns a new dict."""
    text = resources.files(__package__).joinpath(SCHEMA_FILE).read_text(encoding="utf-8")
    result: dict[str, Any] = json.loads(text)
    return result
