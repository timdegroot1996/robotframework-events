"""Screenshots after keywords, for a Playwright-like playback of a test.

Libraries take screenshots only when asked or on failure. With the listener's ``screenshots`` option,
:class:`StepScreenshots` takes one after the keywords of the libraries the user switched on, straight
through the library: no keyword runs and nothing is logged, so ``output.xml`` and ``log.html`` stay as they
are. The listener emits a ``step.screenshot`` event per image.

Which libraries and keywords: :mod:`.config` (presets in ``presets.json``, the user's settings on top).
How: :mod:`.adapters`. Modes: ``actions`` (every keyword of a switched-on library except the excluded ones;
failing keywords always), ``all`` (every keyword, exclusions ignored) and ``failure`` (failing keywords only).

Libraries change fast, so the screenshots never get in the way of a test:

- no screenshot while a JavaScript dialog is open: WebDriver would dismiss it, and the test could not
  handle it anymore
- an adapter adapts to the library's API where it can (Browser's arguments are read from its signature)
- a library whose API does not fit, or whose screenshots keep timing out, is left alone for the rest of the
  run; the listener reports it (console and a ``screenshot.unavailable`` event the Live page shows)
- a screenshot that fails otherwise (no browser open yet, page closed) is skipped
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from . import adapters
from .config import MODES, Config, Preset, build_config, config_from_dict, load_presets, normalize

__all__ = [
    "FOLDER",
    "MODES",
    "Config",
    "StepScreenshots",
    "build_config",
    "config_from_dict",
    "load_presets",
    "normalize",
]

FOLDER = "rfevents-screenshots"

# a screenshot that failed after this long ran into the timeout; this many in a row turn a library off
_SLOW = 1.5
_SLOW_LIMIT = 3
# errors that mean the library's API is not what the adapter expects
_API_ERRORS = (adapters.ApiMismatch, TypeError, AttributeError, ImportError, NameError)

# library: the library or preset name; version; reason
Warn = Callable[[str, str, str], None]


@contextlib.contextmanager
def _no_logging() -> Iterator[None]:
    """Robot Framework logs nothing meanwhile, like Browser does for its secret keywords."""
    try:
        from robot.libraries.BuiltIn import BuiltIn

        output = BuiltIn()._context.output
        previous = output.set_log_level("NONE")
    except Exception:
        yield
        return
    try:
        yield
    finally:
        with contextlib.suppress(Exception):
            output.set_log_level(previous)


def _signatures(instance: Any) -> set[str]:
    """`topmodule:Class` of every class in the library's hierarchy, as presets match them."""
    return {f"{cls.__module__.split('.')[0]}:{cls.__name__}" for cls in type(instance).__mro__}


def _version(instance: Any) -> str:
    try:
        from importlib.metadata import packages_distributions, version

        module = type(instance).__module__.split(".")[0]
        names = packages_distributions().get(module) or [module]
        return version(names[0])
    except Exception:
        return "unknown version"


class StepScreenshots:
    """Takes the screenshots of one run into ``<outdir>/rfevents-screenshots``."""

    def __init__(self, config: Config, outdir: str, warn: Warn) -> None:
        self.config = config
        self.catalog = config.catalog or load_presets()
        self.outdir = Path(outdir)
        self.folder = self.outdir / FOLDER
        self._warn = warn
        self._count = 0
        # library owner name -> (preset, instance), None for libraries that are not switched on
        self._libraries: dict[str, tuple[Preset, Any] | None] = {}
        self._off: set[str] = set()  # presets left alone for the rest of the run
        self._slow: dict[str, int] = {}
        self._last: tuple[Preset, Any] | None = None  # the library of the last screenshot
        for name in config.unknown:
            warn(name, "", "no preset with this name; add it under `custom` to switch it on")

    def after_keyword(self, owner: str, name: str, status: str, tags: list[str]) -> tuple[str, str] | None:
        """The screenshot after a keyword, if it gets one: its path relative to the output directory (with
        ``/``) and the library it was taken with."""
        mode = self.config.mode
        # keywords that did not run (NOT RUN in a branch not taken, after a failure) changed nothing
        if mode == "off" or not owner or status not in ("PASS", "FAIL"):
            return None
        if mode == "failure" and status != "FAIL":
            return None
        library = self._library(owner)
        if library is None:
            # an own keyword the user listed: the page of the library used last
            if mode != "failure" and self._last is not None and self.config.user_included(owner, name):
                return self._take(*self._last)
            return None
        preset, _ = library
        if preset.name in self._off:
            return None
        if mode == "actions" and status != "FAIL":
            if self.config.user_included(owner, name):
                pass
            elif preset.excluded(name, tags) or self.config.user_excluded(owner, name):
                return None
        return self._take(*library)

    def _library(self, owner: str) -> tuple[Preset, Any] | None:
        if owner in self._libraries:
            return self._libraries[owner]
        found: tuple[Preset, Any] | None = None
        try:
            from robot.libraries.BuiltIn import BuiltIn

            instance = BuiltIn().get_library_instance(owner)
        except Exception:
            instance = None
        if instance is not None:
            # libraries used through Remote (JavaFXLibrary, ...) are recognised by their import name
            signatures = _signatures(instance) | {f"name:{normalize(owner)}"}
            for preset in self.config.presets.values():
                if signatures.intersection(preset.match):
                    found = (preset, instance)
                    break
        self._libraries[owner] = found
        return found

    def _take(self, preset: Preset, instance: Any) -> tuple[str, str] | None:
        self._count += 1
        base = self.folder / f"{self._count:05d}"
        started = time.monotonic()
        path = None
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            with _no_logging():
                path = adapters.capture(preset.capture, instance, base, self._borrow)
        except _API_ERRORS as e:
            self._turn_off(preset, instance, f"its API does not fit ({type(e).__name__}: {e})")
        except Exception:
            # no page yet, page closed, ...; a timeout is slow
            if time.monotonic() - started >= _SLOW:
                self._slow[preset.name] = self._slow.get(preset.name, 0) + 1
                if self._slow[preset.name] >= _SLOW_LIMIT:
                    self._turn_off(preset, instance, f"{_SLOW_LIMIT} screenshots in a row timed out")
        if path is None or not path.exists():
            self._count -= 1
            return None
        self._slow[preset.name] = 0
        self._last = (preset, instance)
        return path.relative_to(self.outdir).as_posix(), preset.name

    def _borrow(self, names: list[str]) -> Path | None:
        """A library without its own session (AngularJSLibrary, JupyterLibrary, ...): the screenshot of the
        library it works with (SeleniumLibrary, Browser), when that one is imported."""
        from robot.libraries.BuiltIn import BuiltIn

        wanted = [self.catalog[n] for n in names if n in self.catalog]
        try:
            libraries = BuiltIn().get_library_instance(all=True)
            instances = list(libraries.values()) if isinstance(libraries, dict) else []
        except Exception:
            return None
        for instance in instances:
            signatures = _signatures(instance)
            for preset in wanted:
                if signatures.intersection(preset.match) and preset.capture.get("type") != "borrow":
                    base = self.folder / f"{self._count:05d}"
                    return adapters.capture(preset.capture, instance, base, lambda _names: None)
        return None

    def _turn_off(self, preset: Preset, instance: Any, reason: str) -> None:
        self._off.add(preset.name)
        self._warn(preset.name, _version(instance), reason)
