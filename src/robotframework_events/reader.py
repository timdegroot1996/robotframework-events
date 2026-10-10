"""Reading events files, also while they are being written."""

from __future__ import annotations

import gzip
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import IO

from .events import Event, RunEnded, from_dict


def read_events(
    path: str | os.PathLike[str],
    *,
    follow: bool = False,
    poll: float = 0.1,
    timeout: float | None = None,
    strict: bool = False,
) -> Iterator[Event]:
    """Yields the events of a ``.jsonl`` or ``.jsonl.gz`` file as typed events.

    Lines that are not valid events are skipped, unless ``strict`` is true: then they raise
    ``ValueError``. A last line without a newline is still read when not following.

    With ``follow``, waits for the file to appear and for new lines until ``run.ended``,
    like ``tail -f``. ``timeout`` stops waiting after that many seconds without new data.
    When the file is replaced or truncated (a new run writing to the same path), reading
    starts again from its beginning.
    """
    path = Path(path)
    if path.suffix == ".gz":
        if follow:
            raise ValueError("cannot follow a gzipped file")
        with gzip.open(path, "rt", encoding="utf-8") as file:
            yield from _parse_lines(file, strict)
        return
    if not follow:
        with open(path, encoding="utf-8") as file:
            yield from _parse_lines(file, strict)
        return
    yield from _follow(path, poll, timeout, strict)


def _parse_lines(file: IO[str], strict: bool) -> Iterator[Event]:
    for number, line in enumerate(file, 1):
        event = _parse(line, number, strict)
        if event is not None:
            yield event


def _parse(line: str, number: int, strict: bool) -> Event | None:
    if not line.strip():
        return None
    try:
        return from_dict(json.loads(line))
    except (ValueError, TypeError) as e:
        if strict:
            raise ValueError(f"line {number}: {e}") from None
        return None


def _follow(path: Path, poll: float, timeout: float | None, strict: bool) -> Iterator[Event]:
    last_data = time.monotonic()

    def waited_too_long() -> bool:
        return timeout is not None and time.monotonic() - last_data > timeout

    while not path.exists():
        if waited_too_long():
            return
        time.sleep(poll)

    # binary mode: positions are byte offsets, and a partly written UTF-8 character stays in the buffer
    file = open(path, "rb")  # noqa: SIM115 reopened when the file is replaced
    try:
        identity = os.fstat(file.fileno())
        buffer = b""
        number = 0
        while True:
            chunk = file.readline()
            if chunk:
                last_data = time.monotonic()
                buffer += chunk
                if not buffer.endswith(b"\n"):
                    continue  # the writer has not finished this line yet
                number += 1
                event = _parse(buffer.decode("utf-8", errors="replace"), number, strict)
                buffer = b""
                if event is not None:
                    yield event
                    if isinstance(event, RunEnded):
                        return
                continue
            if waited_too_long():
                return
            time.sleep(poll)
            if _replaced(path, file, identity):
                file.close()
                file = open(path, "rb")  # noqa: SIM115
                identity = os.fstat(file.fileno())
                buffer = b""
                number = 0
    finally:
        file.close()


def _replaced(path: Path, file: IO[bytes], identity: os.stat_result) -> bool:
    try:
        current = os.stat(path)
    except OSError:
        return False
    if (current.st_ino, current.st_dev) != (identity.st_ino, identity.st_dev) and current.st_ino:
        return True
    return current.st_size < file.tell()
