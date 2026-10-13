"""Listener v3 that emits execution events as JSON Lines (format v1, see events-v1.schema.json)."""

from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import sys
import threading
import time
import uuid
from collections.abc import Callable
from json.encoder import encode_basestring as _quote
from pathlib import Path
from typing import Any, BinaryIO

from robot import result, running
from robot.version import VERSION as ROBOT_VERSION

from .screenshots import StepScreenshots, build_config

FORMAT_VERSION = 1
MIN_RF_VERSION = (7, 0)

EventCallback = Callable[[dict[str, Any]], None]

_callbacks: list[EventCallback] = []

# IF/ELSE and TRY/EXCEPT roots are not emitted; their branches are numbered and
# parented as children of the root's parent, as in output.xml and log.html.
ROOT_TYPES = frozenset({"IF/ELSE ROOT", "TRY/EXCEPT ROOT"})
CONTROL_TYPES = frozenset(
    {
        "FOR",
        "ITERATION",
        "IF",
        "ELSE IF",
        "ELSE",
        "TRY",
        "EXCEPT",
        "FINALLY",
        "WHILE",
        "GROUP",
        "VAR",
        "RETURN",
        "BREAK",
        "CONTINUE",
        "ERROR",
    }
)
LEVELS = {"TRACE": 0, "DEBUG": 1, "INFO": 2, "WARN": 3, "ERROR": 4, "FAIL": 4, "SKIP": 2}
MAX_ARGS = 20
MAX_ARG_LENGTH = 200


def add_callback(callback: EventCallback) -> None:
    """Call ``callback(event)`` for every event emitted by any Listener in this process."""
    if callback not in _callbacks:
        _callbacks.append(callback)


def remove_callback(callback: EventCallback) -> None:
    if callback in _callbacks:
        _callbacks.remove(callback)


def _check_robot_version(version: str) -> None:
    match = re.match(r"(\d+)\.(\d+)", version)
    if match and (int(match.group(1)), int(match.group(2))) < MIN_RF_VERSION:
        raise RuntimeError(
            f"robotframework-events requires Robot Framework {'.'.join(map(str, MIN_RF_VERSION))} or newer, "
            f"found {version}."
        )


def _stats(suite: result.TestSuite) -> dict[str, int]:
    s = suite.statistics
    return {"total": s.total, "passed": s.passed, "failed": s.failed, "skipped": s.skipped}


def _bool(value: Any) -> bool:
    return str(value).strip().lower() not in ("false", "off", "no", "0", "none", "")


def _normalize(text: str) -> str:
    return "".join(str(text).lower().split())


def _short(value: Any, limit: int = MAX_ARG_LENGTH) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _short_list(values: Any) -> list[str] | None:
    if not values:
        return None
    items = [_short(v) for v in list(values)[:MAX_ARGS]]
    if len(values) > MAX_ARGS:
        items.append("…")
    return items


def _clean(fields: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in fields.items() if v is not None and v != ""}


def step_fields(kind: str, result: Any, args: bool = True) -> dict[str, Any]:
    """Kind-specific fields of a step.started event, from a result model body item.

    Fields without a value are left out. Keywords and loop iterations are by far the most
    common steps, so they are built without intermediate values.
    """
    if kind in KEYWORD_TYPES:
        fields: dict[str, Any] = {}
        name = result.name
        if name:
            fields["name"] = name
        owner = result.owner
        if owner:
            fields["owner"] = owner
        if args:
            values = result.args
            if values:
                fields["args"] = _short_list(values)
        assign = result.assign
        if assign:
            fields["assign"] = list(assign)
        tags = result.tags
        # children of a flattened keyword are emitted live but are not in output.xml or log.html
        if tags and any(_normalize(t) == "robot:flatten" for t in tags):
            fields["flatten"] = True
        return fields
    if kind == "ITERATION":
        assign = getattr(result, "assign", None)
        return {"assign": {k: _short(v) for k, v in assign.items()}} if assign else {}
    if kind == "FOR":
        return _clean({"assign": list(result.assign), "flavor": result.flavor, "values": _short_list(result.values)})
    if kind in ("IF", "ELSE IF"):
        return _clean({"condition": result.condition})
    if kind == "WHILE":
        return _clean({"condition": result.condition, "limit": result.limit})
    if kind == "EXCEPT":
        return _clean({"patterns": list(result.patterns), "assign": result.assign})
    if kind == "GROUP":
        return _clean({"name": result.name})
    if kind == "VAR":
        return _clean({"name": result.name, "values": _short_list(result.value), "scope": result.scope})
    if kind in ("RETURN", "ERROR"):
        return _clean({"values": _short_list(result.values)})
    return {}


# Step events are almost all events. Writing them from a template is about twice as fast as the
# general encoder. Ids, kinds and statuses need no escaping; other strings go through _quote.
# Anything unexpected (another kind, an unknown field, a value of another type) returns None
# and is written by the general encoder instead.
KEYWORD_TYPES = frozenset({"KEYWORD", "SETUP", "TEARDOWN"})


def _step_started_json(e: dict[str, Any]) -> str | None:
    kind = e["kind"]
    if kind not in KEYWORD_TYPES and kind != "ITERATION":
        return None
    s = f'{{"v":{e["v"]},"seq":{e["seq"]},"t":{e["t"]!r},"type":"step.started","id":"{e["id"]}"'
    written = 6
    if "parent" in e:
        s += f',"parent":"{e["parent"]}"'
        written += 1
    s += f',"kind":"{kind}"'
    if "source" in e:
        s += f',"source":{_quote(e["source"])}'
        written += 1
    if "lineno" in e:
        s += f',"lineno":{int(e["lineno"])}'
        written += 1
    if kind == "ITERATION":
        if "assign" in e:
            s += ',"assign":{' + ",".join(f"{_quote(k)}:{_quote(v)}" for k, v in e["assign"].items()) + "}"
            written += 1
    else:
        for key in ("name", "owner"):
            if key in e:
                s += f',"{key}":{_quote(e[key])}'
                written += 1
        for key in ("args", "assign"):
            if key in e:
                s += f',"{key}":[{",".join(map(_quote, e[key]))}]'
                written += 1
        if e.get("flatten") is True:
            s += ',"flatten":true'
            written += 1
    return s + "}" if written == len(e) else None


def _step_ended_json(e: dict[str, Any]) -> str | None:
    s = f'{{"v":{e["v"]},"seq":{e["seq"]},"t":{e["t"]!r},"type":"step.ended","id":"{e["id"]}","status":"{e["status"]}"'
    written = 7
    if "message" in e:
        s += f',"message":{_quote(e["message"])}'
        written += 1
    s += f',"elapsed":{float(e["elapsed"])!r}}}'
    return s if written == len(e) else None


# Without callbacks no event dict is needed: keyword and iteration steps are written straight from
# the model, field for field as _step_started_json and _step_ended_json write them. ``t`` is the
# time already formatted (see Listener._time). A value of an unexpected type raises, and the caller
# then builds the dict. Few concatenations: every one copies the line.
def _step_started_line(
    seq: int, t: str, id: str, parent: str | None, kind: str, source: str | None, lineno: Any, result: Any, args: bool
) -> str:
    if parent is not None:
        s = (
            f'{{"v":{FORMAT_VERSION},"seq":{seq},"t":{t},"type":"step.started","id":"{id}",'
            f'"parent":"{parent}","kind":"{kind}"'
        )
    else:
        s = f'{{"v":{FORMAT_VERSION},"seq":{seq},"t":{t},"type":"step.started","id":"{id}","kind":"{kind}"'
    if kind in KEYWORD_TYPES:
        # in a loop the same keyword call comes back with the same fields
        values = result.args if args else None
        key = (source, lineno, result.name, result.owner, values, result.assign)
        rest = _keyword_fields.get(key)
        if rest is None:
            rest = _keyword_started_fields(source, lineno, result, values)
            if len(_keyword_fields) >= 4096:
                _keyword_fields.clear()
            _keyword_fields[key] = rest
        return s + rest
    # ITERATION
    if source:
        s += ',"source":' + _quote(source)
    if lineno is not None:
        s += f',"lineno":{lineno:d}'
    assign = getattr(result, "assign", None)
    if assign and len(assign) == 1:  # the common FOR loop: one variable
        ((k, v),) = assign.items()
        if type(v) is not str or len(v) > MAX_ARG_LENGTH:
            v = _short(v)
        s += f',"assign":{{{_quote(k)}:{_quote(v)}}}'
    elif assign:
        s += (
            ',"assign":{'
            + ",".join(
                [
                    f"{_quote(k)}:{_quote(v if type(v) is str and len(v) <= MAX_ARG_LENGTH else _short(v))}"
                    for k, v in assign.items()
                ]
            )
            + "}"
        )
    return s + "}\n"


# The fields of a keyword's step.started after "kind", by call site. Tags are not in the key: a
# keyword (name and owner) has the same tags on every call.
_keyword_fields: dict[tuple[Any, ...], str] = {}


def _keyword_started_fields(source: str | None, lineno: Any, result: Any, values: Any) -> str:
    s = ""
    if source:
        s += ',"source":' + _quote(source)
    if lineno is not None:
        s += f',"lineno":{lineno:d}'
    name = result.name
    owner = result.owner
    if name and owner:
        s += f',"name":{_quote(name)},"owner":{_quote(owner)}'
    elif name:
        s += ',"name":' + _quote(name)
    elif owner:
        s += ',"owner":' + _quote(owner)
    if values:
        s += ',"args":[' + ",".join(map(_quote, _short_list(values))) + "]"  # type: ignore[arg-type]
    assign = result.assign
    if assign:
        s += ',"assign":[' + ",".join(map(_quote, assign)) + "]"
    tags = result.tags
    if tags and any(_normalize(t) == "robot:flatten" for t in tags):
        s += ',"flatten":true'
    return s + "}\n"


def _step_ended_line(seq: int, t: str, id: str | None, status: str, message: str, elapsed: float) -> str:
    if message:
        return (
            f'{{"v":{FORMAT_VERSION},"seq":{seq},"t":{t},"type":"step.ended","id":"{id}","status":"{status}",'
            f'"message":{_quote(message)},"elapsed":{elapsed:.4f}}}\n'
        )
    return (
        f'{{"v":{FORMAT_VERSION},"seq":{seq},"t":{t},"type":"step.ended","id":"{id}","status":"{status}",'
        f'"elapsed":{elapsed:.4f}}}\n'
    )


def default_events_file(outdir: str, output: str | None) -> Path:
    """Where the listener writes by default: named after the output file, the way robotdashboard
    finds a run's ``log.html`` (``output`` -> ``log``), so tools can find a run's events from its output."""
    if not output or str(output).upper() == "NONE":
        return Path(outdir) / "events.jsonl"
    output_path = Path(output)
    return output_path.with_name(output_path.name.replace("output", "events")).with_suffix(".jsonl")


class _Frame:
    """One open suite, test or step on the stack.

    ``id`` is None for IF/TRY roots; ``owner`` then points to the frame whose
    child counter the root's branches share. ``emitted`` is False for roots and
    for structures hidden with ``structures=false``. ``keyword`` is True for keywords,
    the only steps whose children can come from another file.
    """

    __slots__ = ("children", "emitted", "id", "keyword", "owner", "pid", "source")

    def __init__(
        self,
        id: str | None,
        source: str | None,
        parent: _Frame | None,
        owner: _Frame | None = None,
        emitted: bool = True,
        keyword: bool = False,
    ) -> None:
        self.id = id
        self.keyword = keyword
        self.children = 0
        self.owner = owner
        self.source = source
        self.emitted = emitted
        # id of the nearest emitted frame, this one included: the parent of anything started inside it
        self.pid: str | None = id if emitted else (parent.pid if parent else None)


class Listener:
    """Writes one JSON object per line for the run, suites, tests, steps and log messages.

    Arguments (``Listener:name=value:name=value``):

    - ``file``: path of the JSONL file. Default: next to the output file, named like it with
      ``output`` replaced by ``events`` (``output.xml`` -> ``events.jsonl``, ``output-1.xml`` ->
      ``events-1.jsonl``); ``${OUTPUT DIR}/events.jsonl`` with ``--output NONE``.
      ``NONE`` disables the file (callbacks still get events).
    - ``level``: minimum level of logged messages, default ``INFO``.
    - ``messages``: emit ``message.logged`` events, default ``true``.
    - ``args``: include keyword arguments, default ``true``.
    - ``structures``: emit control structures (FOR, IF, TRY, ...), default ``true``.
      Keywords inside them are still emitted, parented to the nearest emitted step.
    - ``max_text``: maximum length of message texts, default 4096.
    - ``flush``: seconds between flushes of the file while events come in, default 0.1, so a reader that
      follows the file sees the keyword that is running. ``0`` flushes only after every test and at the end.
    - ``screenshots``: a screenshot after the keywords of the libraries named in ``screenshot_libraries``, for a
      playback of the test: ``off`` (default), ``actions`` (every keyword except the read-only ones its
      preset or the user excludes, and failures), ``all`` or ``failure``; or the path of a JSON file with the
      mode, libraries and keyword lists (see :mod:`robotframework_events.screenshots.config`). Saved in
      ``${OUTPUT DIR}/rfevents-screenshots/``, announced with ``step.screenshot`` events, not added to
      ``log.html``. Each screenshot takes time.
    - ``screenshot_libraries``: the libraries that get screenshots, comma separated (``Browser,SeleniumLibrary``);
      none by default.
    """

    ROBOT_LISTENER_API_VERSION = 3
    # Run after listeners that modify results.
    ROBOT_LISTENER_PRIORITY = -1000

    def __init__(
        self,
        file: str | None = None,
        level: str = "INFO",
        messages: str = "true",
        args: str = "true",
        structures: str = "true",
        max_text: str = "4096",
        flush: str = "0.1",
        screenshots: str = "off",
        screenshot_libraries: str | None = None,
    ) -> None:
        _check_robot_version(ROBOT_VERSION)
        self._file_option = file
        self._min_level = LEVELS.get(level.upper(), 2)
        self._messages = _bool(messages)
        self._args = _bool(args)
        self._structures = _bool(structures)
        self._max_text = int(max_text)
        self._flush_interval = float(flush)
        self._screenshots = build_config(screenshots, screenshot_libraries)
        self._shots: StepScreenshots | None = None
        # binary: BufferedWriter is thread-safe, so the flush thread needs no lock on the write path
        self._out: BinaryIO | None = None
        self._dirty = False
        self._stop_flushing = threading.Event()
        self._flusher: threading.Thread | None = None
        self._seq = 0
        self._run_id = str(uuid.uuid4())
        self._started = False
        self._root: result.TestSuite | None = None
        self._stack: list[_Frame] = []
        # last emitted status and message of every suite and test, to detect changes made by suite teardowns
        self._statuses: dict[str, tuple[str, str]] = {}
        self._encode = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"), default=str).encode
        # data.source walks up the model on every call; siblings share their parent, so cache per parent
        self._source_parent: Any = None
        self._source_value: str | None = None
        # the time of step events, formatted once per millisecond: [_t_low, _t_high) formats as _t_text
        self._t_low = self._t_high = 0.0
        self._t_text = ""

    # --- emitting -------------------------------------------------------------

    def _time(self) -> str:
        t = time.time()
        if not self._t_low <= t < self._t_high:
            # formatted, not rounded (three times faster): the text can end in zeros
            self._t_text = text = f"{t:.3f}"
            value = float(text)
            self._t_low, self._t_high = value - 0.0005, value + 0.0005
        return self._t_text

    def _new(self, type_: str) -> dict[str, Any]:
        self._seq += 1
        return {"v": FORMAT_VERSION, "seq": self._seq, "t": round(time.time(), 3), "type": type_}

    def _emit(self, type_: str, **fields: Any) -> None:
        """Emits an event; fields that are None or empty are left out."""
        event = self._new(type_)
        for key, value in fields.items():
            if value is not None and value != "":
                event[key] = value
        self._write(event)

    def _write(self, event: dict[str, Any], template: Callable[[dict[str, Any]], str | None] | None = None) -> None:
        if self._out is not None:
            line = None
            if template is not None:
                try:
                    line = template(event)
                except (TypeError, ValueError, AttributeError):  # an unexpected value: use the encoder
                    line = None
            try:
                self._out.write(((line if line is not None else self._encode(event)) + "\n").encode("utf-8"))
                self._dirty = True
            except OSError as e:
                self._write_failed(e)

        if not _callbacks:
            return
        for callback in list(_callbacks):
            try:
                callback(event)
            except Exception as e:  # never raise into Robot Framework
                print(f"robotframework-events: removing failing callback: {e}", file=sys.__stderr__)
                remove_callback(callback)

    def _write_failed(self, error: OSError) -> None:
        print(f"robotframework-events: disabling file output: {error}", file=sys.__stderr__)
        self._out = None

    def _flush(self) -> None:
        out = self._out
        if out is not None:
            self._dirty = False
            with contextlib.suppress(OSError, ValueError):  # ValueError: closed meanwhile
                out.flush()

    def _flush_loop(self) -> None:
        while not self._stop_flushing.wait(self._flush_interval):
            if self._dirty:
                self._flush()

    def _output_locations(self) -> tuple[str, str | None]:
        """${OUTPUT DIR} and ${OUTPUT FILE} of the run (cwd and None when they cannot be read)."""
        from robot.libraries.BuiltIn import BuiltIn

        try:
            outdir = BuiltIn().get_variable_value("${OUTPUT DIR}") or os.getcwd()
            output = BuiltIn().get_variable_value("${OUTPUT FILE}")
        except Exception:
            return os.getcwd(), None
        return str(outdir), output

    def _pabot(self) -> dict[str, Any] | None:
        """The pabot item this process runs (pabot passes it as variables), None outside pabot."""
        from robot.libraries.BuiltIn import BuiltIn

        try:
            index = BuiltIn().get_variable_value("${PABOTQUEUEINDEX}")
            if index is None:
                return None
            pool = BuiltIn().get_variable_value("${PABOTEXECUTIONPOOLID}")
            processes = BuiltIn().get_variable_value("${PABOTNUMBEROFPROCESSES}")
            last = BuiltIn().get_variable_value("${PABOTISLASTEXECUTIONINPOOL}")
            item: dict[str, Any] = {"index": int(index)}
            if pool is not None:
                item["pool"] = int(pool)
            if processes is not None:
                item["processes"] = int(processes)
            if last is not None:
                item["last"] = str(last) == "1"
            return item
        except Exception:
            return None

    def _open_file(self, outdir: str, output: str | None) -> None:
        if self._file_option and self._file_option.upper() == "NONE":
            return
        path = Path(self._file_option) if self._file_option else default_events_file(outdir, output)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # buffered; flushed every `flush` seconds, after every test and at close so tailing readers see progress
            self._out = open(path, "wb", buffering=1 << 16)  # noqa: SIM115 closed in close()
        except OSError as e:
            print(f"robotframework-events: cannot open {path}: {e}", file=sys.__stderr__)
            return
        if self._flush_interval > 0:
            self._flusher = threading.Thread(target=self._flush_loop, name="robotframework-events-flush", daemon=True)
            self._flusher.start()

    def _parent_id(self) -> str | None:
        return self._stack[-1].pid if self._stack else None

    def _data_source(self, data: Any) -> str | None:
        parent = getattr(data, "parent", None)
        if parent is None or parent is not self._source_parent:
            try:
                source = data.source
            except Exception:
                source = None
            self._source_parent = parent
            self._source_value = str(source) if source else None
        return self._source_value

    # --- suites and tests -------------------------------------------------------

    def start_suite(self, data: running.TestSuite, result: result.TestSuite) -> None:
        if not self._started:
            self._started = True
            self._root = result
            outdir, output = self._output_locations()
            self._open_file(outdir, output)
            self._emit(
                "run.started",
                run=self._run_id,
                rf=ROBOT_VERSION,
                python=platform.python_version(),
                pid=os.getpid(),
                cwd=os.getcwd(),
                # log.html links screenshots and other files relative to it
                outputdir=outdir,
                # viewers merge the items of one pabot run into one run
                pabot=self._pabot(),
            )
            if self._screenshots.mode != "off":
                if not self._screenshots.active:
                    self._screenshot_unavailable(
                        "", "", "screenshots are on, but no library is named (screenshot_libraries=Browser,...)"
                    )
                else:
                    self._shots = StepScreenshots(self._screenshots, outdir, self._screenshot_unavailable)
        source = str(data.source) if data.source else None
        self._emit(
            "suite.started",
            id=data.id,
            parent=self._parent_id(),
            name=result.name,
            longname=result.full_name,
            source=source,
            tests=data.test_count,
            # the top-level suite lists every test the run will execute, for time estimates
            planned=[test.full_name for test in data.all_tests] if not self._stack else None,
        )
        self._stack.append(_Frame(data.id, source, self._stack[-1] if self._stack else None))

    def end_suite(self, data: running.TestSuite, result: result.TestSuite) -> None:
        self._stack.pop()
        if result.has_teardown and result.teardown.status in ("FAIL", "SKIP"):
            self._emit_status_changes(result)
        self._statuses[data.id] = (result.status, result.message)
        self._emit(
            "suite.ended",
            id=data.id,
            status=result.status,
            message=result.message,
            elapsed=round(result.elapsed_time.total_seconds(), 3),
            stats=_stats(result),
        )

    def _emit_status_changes(self, suite: result.TestSuite) -> None:
        """A failing or skipping suite teardown changes the status or message of tests and suites that already ended."""
        for child in suite.suites:
            self._status_change(child, "suite")
            self._emit_status_changes(child)
        for test in suite.tests:
            self._status_change(test, "test")

    def _status_change(self, item: result.TestSuite | result.TestCase, kind: str) -> None:
        current = (item.status, item.message)
        if self._statuses.get(item.id, current) != current:
            self._statuses[item.id] = current
            self._emit("status.changed", id=item.id, item=kind, status=item.status, message=item.message)

    def start_test(self, data: running.TestCase, result: result.TestCase) -> None:
        source = str(data.source) if data.source else None
        self._emit(
            "test.started",
            id=data.id,
            parent=self._parent_id(),
            name=result.name,
            longname=result.full_name,
            source=source,
            lineno=data.lineno,
            tags=list(data.tags) or None,
        )
        self._stack.append(_Frame(data.id, source, self._stack[-1] if self._stack else None))

    def end_test(self, data: running.TestCase, result: result.TestCase) -> None:
        self._stack.pop()
        self._statuses[data.id] = (result.status, result.message)
        self._emit(
            "test.ended",
            id=data.id,
            status=result.status,
            message=result.message,
            elapsed=round(result.elapsed_time.total_seconds(), 3),
        )
        self._flush()

    # --- steps ------------------------------------------------------------------

    def start_body_item(self, data: Any, result: Any) -> None:
        parent = self._stack[-1] if self._stack else _Frame("s1", None, None)
        kind = result.type

        if kind in ROOT_TYPES:
            self._stack.append(_Frame(None, parent.source, parent, owner=parent.owner or parent, emitted=False))
            return

        counter = parent.owner or parent
        counter.children += 1
        item_id = f"{counter.id}-k{counter.children}"
        # data.source walks up the model, and in FOR loops data is new every iteration;
        # only a keyword's children (a user keyword's body) can be in another file
        source = self._data_source(data) if parent.keyword else parent.source

        if kind in CONTROL_TYPES and not self._structures:
            # ids stay exact, but the structure is hidden: its children attach to the nearest emitted step
            self._stack.append(_Frame(item_id, source or parent.source, parent, emitted=False))
            return

        new_source = source if source and source != parent.source else None
        lineno = getattr(data, "lineno", None)
        line = None
        if self._out is not None and not _callbacks and (kind in KEYWORD_TYPES or kind == "ITERATION"):
            # the most frequent event: written as a line without an event dict
            try:
                line = _step_started_line(
                    self._seq + 1, self._time(), item_id, parent.pid, kind, new_source, lineno, result, self._args
                )
            except (TypeError, ValueError, AttributeError):  # an unexpected value: the event dict and the encoder
                line = None
        if line is not None:
            self._seq += 1
            try:  # inlined: a call per event is measurable
                self._out.write(line.encode("utf-8"))  # type: ignore[union-attr]
                self._dirty = True
            except OSError as e:
                self._write_failed(e)
        else:
            event = self._new("step.started")
            event["id"] = item_id
            if parent.pid is not None:
                event["parent"] = parent.pid
            event["kind"] = kind
            if new_source:
                event["source"] = new_source
            if lineno is not None:
                event["lineno"] = lineno
            event.update(step_fields(kind, result, self._args))
            self._write(event, _step_started_json)
        # positional: keyword arguments make this call measurably slower
        self._stack.append(_Frame(item_id, source or parent.source, parent, None, True, kind in KEYWORD_TYPES))

    def end_body_item(self, data: Any, result: Any) -> None:
        frame = self._stack.pop()
        if not frame.emitted:
            return
        message = result.message
        elapsed = result.elapsed_time.total_seconds()
        line = None
        if self._out is not None and not _callbacks:
            try:
                line = _step_ended_line(self._seq + 1, self._time(), frame.id, result.status, message, elapsed)
            except (TypeError, ValueError, AttributeError):
                line = None
        if line is not None:
            self._seq += 1
            try:  # inlined: a call per event is measurable
                self._out.write(line.encode("utf-8"))  # type: ignore[union-attr]
                self._dirty = True
            except OSError as e:
                self._write_failed(e)
        else:
            event = self._new("step.ended")
            event["id"] = frame.id
            event["status"] = result.status
            if message:
                event["message"] = message
            event["elapsed"] = round(elapsed, 4)
            self._write(event, _step_ended_json)
        if self._shots is not None and result.type in KEYWORD_TYPES:
            self._screenshot(frame.id, result)

    def _screenshot(self, step_id: str | None, result: Any) -> None:
        if step_id is None or self._shots is None:
            return
        owner = getattr(result, "owner", None) or ""
        taken = self._shots.after_keyword(owner, result.name or "", result.status, list(result.tags))
        if taken is not None:
            self._emit("step.screenshot", id=step_id, path=taken[0], library=taken[1])

    def _screenshot_unavailable(self, library: str, version: str, reason: str) -> None:
        """Screenshots that do not work are reported, so users notice and can report it."""
        what = f"{library} {version}".strip()
        print(
            f"robotframework-events: no step screenshots{f' with {what}' if what else ''}: {reason}",
            file=sys.__stderr__,
        )
        if self._started:
            self._emit("screenshot.unavailable", library=library, version=version, reason=reason)

    # --- messages and result files ---------------------------------------------------

    def log_message(self, message: Any) -> None:
        if not self._messages or LEVELS.get(message.level, 2) < self._min_level:
            return
        text = message.message or ""
        truncated = len(text) > self._max_text
        self._emit(
            "message.logged",
            parent=self._parent_id(),  # message.parent is not set yet when listeners are called
            level=message.level,
            text=text[: self._max_text] if truncated else text,
            truncated=True if truncated else None,
            html=True if message.html else None,
        )

    def _result_file(self, kind: str, path: Any) -> None:
        self._emit("resultfile.created", kind=kind, path=str(path))

    def output_file(self, path: Any) -> None:
        self._result_file("OUTPUT", path)

    def log_file(self, path: Any) -> None:
        self._result_file("LOG", path)

    def report_file(self, path: Any) -> None:
        self._result_file("REPORT", path)

    def xunit_file(self, path: Any) -> None:
        self._result_file("XUNIT", path)

    def debug_file(self, path: Any) -> None:
        self._result_file("DEBUG", path)

    def close(self) -> None:
        if self._root is not None:
            self._emit("run.ended", status=self._root.status, stats=_stats(self._root))
        if self._flusher is not None:
            self._stop_flushing.set()
            self._flusher.join()
            self._flusher = None
        if self._out is not None:
            self._out.close()
            self._out = None
