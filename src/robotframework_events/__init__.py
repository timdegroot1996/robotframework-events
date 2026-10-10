"""Robot Framework execution events as JSON Lines.

Usage::

    robot --listener robotframework_events.Listener tests/
    robot --listener robotframework_events.Listener:file=results/events.jsonl tests/

Programs that run Robot Framework in the same process (for example robotcode's
debugger) can receive every event with :func:`add_callback`. Programs that read
events files can use the typed classes in :mod:`robotframework_events.events`.
"""

from .events import Event, from_dict, schema
from .listener import Listener, add_callback, remove_callback

__all__ = ["Event", "Listener", "add_callback", "from_dict", "remove_callback", "schema"]
__version__ = "0.0.1"
