"""Robot Framework execution events as JSON Lines.

Usage::

    robot --listener robotframework_events.Listener tests/
    robot --listener robotframework_events.Listener:file=results/events.jsonl tests/

Programs that run Robot Framework in the same process (for example robotcode's
debugger) can receive every event with :func:`add_callback`. Programs that read
events files use :func:`read_events` and :class:`RunState`.
"""

from .convert import convert
from .events import Event, from_dict, schema
from .listener import Listener, add_callback, remove_callback
from .reader import read_events
from .state import RunState

__all__ = [
    "Event",
    "Listener",
    "RunState",
    "add_callback",
    "convert",
    "from_dict",
    "read_events",
    "remove_callback",
    "schema",
]
__version__ = "0.1.0"
