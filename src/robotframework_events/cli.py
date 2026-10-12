"""The ``rfevents`` command: ``tail`` shows a run in the terminal, ``convert`` builds events from a result file."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from collections.abc import Iterable
from typing import TextIO

from . import __version__
from .convert import convert
from .events import (
    Event,
    MessageLogged,
    RunEnded,
    StepStarted,
    SuiteEnded,
    SuiteStarted,
    TestEnded,
    TestStarted,
)
from .listener import LEVELS
from .reader import read_events
from .rebuild import write_rebuilt
from .state import RunState, step_label

COLORS = {"PASS": "32", "FAIL": "31", "SKIP": "33", "NOT RUN": "90", "WARN": "33", "ERROR": "31"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rfevents", description="Robot Framework execution events.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    tail = commands.add_parser("tail", help="show a run from its events file, readable")
    tail.add_argument("file", help="events file (.jsonl or .jsonl.gz)")
    tail.add_argument("-f", "--follow", action="store_true", help="wait for new events until the run ends")
    tail.add_argument(
        "--steps",
        type=int,
        default=1,
        metavar="DEPTH",
        help="show steps this many levels below each test, 0 for none (default 1)",
    )
    tail.add_argument(
        "--level",
        default="WARN",
        type=str.upper,
        choices=list(LEVELS),
        help="show log messages from this level (default WARN)",
    )
    tail.add_argument("--color", choices=["auto", "always", "never"], default="auto")

    conv = commands.add_parser("convert", help="build events from output.xml or output.json")
    conv.add_argument("output", help="output.xml or output.json")
    conv.add_argument("-o", "--outfile", help="events file to write (default: standard output)")

    rebuilt = commands.add_parser(
        "rebuild", help="build output.xml from events, for a run that crashed or was killed before writing it"
    )
    rebuilt.add_argument("file", help="events file (.jsonl or .jsonl.gz)")
    rebuilt.add_argument("-o", "--outfile", required=True, help="output.xml to write")

    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")
    try:
        if args.command == "tail":
            color = args.color == "always" or (
                args.color == "auto" and sys.stdout.isatty() and "NO_COLOR" not in os.environ
            )
            Tail(sys.stdout, args.steps, args.level, color).show(read_events(args.file, follow=args.follow))
        elif args.command == "rebuild":
            write_rebuilt(read_events(args.file), args.outfile)
        else:
            write_converted(args.output, args.outfile)
    except KeyboardInterrupt:
        return 130
    except OutputClosed:
        # keep Python from failing again when it flushes stdout at exit
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
        return 0
    except (OSError, ValueError) as e:
        print(f"rfevents: {e}", file=sys.stderr)
        return 2
    return 0


def write_converted(output: str, outfile: str | None) -> None:
    encode = json.JSONEncoder(ensure_ascii=False, separators=(",", ":")).encode
    lines = (encode(event) + "\n" for event in convert(output))
    if outfile is None:
        sys.stdout.writelines(lines)
        return
    with open(outfile, "w", encoding="utf-8") as file:
        file.writelines(lines)


class OutputClosed(Exception):
    pass


class Tail:
    """Prints suites, tests, top-level steps, failures and warnings as they happen."""

    def __init__(self, out: TextIO, steps: int = 1, level: str = "WARN", color: bool = False) -> None:
        self.out = out
        self.steps = steps
        self.level = LEVELS[level]
        self.color = color
        self.state = RunState()

    def show(self, events: Iterable[Event]) -> None:
        for event in events:
            self.state.apply(event)
            self.print_event(event)

    def print_event(self, event: Event) -> None:
        if isinstance(event, SuiteStarted):
            self.line(self.indent(event.id), event.longname if event.parent is None else event.name)
        elif isinstance(event, TestStarted):
            self.line(self.indent(event.id), event.name)
        elif isinstance(event, StepStarted):
            depth = self.step_depth(event.id)
            if depth <= self.steps:
                node = self.state.nodes[event.id]
                kind = "" if event.kind == "KEYWORD" else ("ITER" if event.kind == "ITERATION" else event.kind)
                parts = [kind, step_label(node), *(event.args or [])]
                self.line(self.indent(event.id), "    ".join(p for p in parts if p))
        elif isinstance(event, TestEnded):
            node = self.state.nodes[event.id]
            self.line(
                self.indent(event.id), self.paint(node.status, node.status), node.name, f"({event.elapsed:.2f} s)"
            )
            if node.message:
                self.line(self.indent(event.id) + "  ", node.message)
        elif isinstance(event, SuiteEnded):
            node = self.state.nodes[event.id]
            if node.parent is not None:
                return
            s = event.stats
            self.line(
                "",
                self.paint(node.status, node.status),
                getattr(node.started, "longname", node.name),
                f"{s['total']} tests, {s['passed']} passed, {s['failed']} failed, {s['skipped']} skipped",
            )
        elif isinstance(event, MessageLogged):
            if LEVELS.get(event.level, 2) >= self.level and event.parent in self.state.nodes:
                self.line(
                    self.indent(self.shown(event.parent)) + "  ",
                    self.paint(event.level, f"[{event.level}]"),
                    event.text or "",
                )
        elif isinstance(event, RunEnded):
            self.out.flush()

    def indent(self, node_id: str | None) -> str:
        return "  " * (len(self.state.path(node_id or "")) - 1)

    def shown(self, node_id: str | None) -> str | None:
        """The node, or its nearest ancestor that is printed."""
        for node in reversed(self.state.path(node_id or "")):
            if node.kind in ("SUITE", "TEST") or self.step_depth(node.id) <= self.steps:
                return node.id
        return node_id

    def step_depth(self, node_id: str) -> int:
        """1 for steps directly in a test or suite, 2 for their children, ..."""
        return sum(1 for node in self.state.path(node_id) if node.kind not in ("SUITE", "TEST"))

    def paint(self, status: str, text: str) -> str:
        code = COLORS.get(status)
        return f"\033[{code}m{text}\033[0m" if self.color and code else text

    def line(self, indent: str, *parts: str) -> None:
        self.out.write(indent + "  ".join(p for p in parts if p) + "\n")
        self.out.flush()


if __name__ == "__main__":
    sys.exit(main())
