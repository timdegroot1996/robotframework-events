"""Which libraries and keywords get a step screenshot: the presets (``presets.json``) with the user's settings on top.

Libraries are opt-in: none gets screenshots until it is named. Keywords are opt-out: in a library that is
switched on every keyword gets one, except those its preset or the user excludes. ``include`` adds own
keywords (from resource files), which use the session of the library that took the last screenshot.

The settings come from the listener's arguments (``screenshots=actions;screenshot_libraries=Browser``) or
from a JSON file (``screenshots=path/to/screenshots.json``)::

    {
      "version": 1,
      "mode": "actions",
      "libraries": ["Browser", "SeleniumLibrary"],
      "include": ["MyShop.Log In"],
      "exclude": ["Browser.Hover", "Scroll To *"],
      "custom": {
        "MyDesktopLibrary": {"match": ["mydesktop:MyDesktopLibrary"], "capture": {"type": "screen"}}
      }
    }

``custom`` adds libraries without a preset, or replaces a preset with the same name; its entries are named
in ``libraries`` like the presets.
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

MODES = ("off", "actions", "all", "failure")
CONFIG_VERSION = 1
CAPTURE_TYPES = ("browser", "webdriver", "borrow", "method", "screen", "qweb", "sapgui")


def normalize(name: str) -> str:
    """A keyword or library name compared without case, with underscores as spaces and single spaces, so
    `Get_Text` and `get  text` match `Get Text` while `Log *` still does not match `Login`."""
    return re.sub(r"\s+", " ", name.replace("_", " ")).strip().lower()


@dataclass(frozen=True)
class Preset:
    """How screenshots work for one library."""

    name: str
    match: tuple[str, ...]
    capture: dict[str, Any]
    exclude: tuple[str, ...] = ()
    exclude_tags: frozenset[str] = frozenset()
    aliases: tuple[str, ...] = ()
    tested: str | None = None

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Preset:
        capture = dict(data.get("capture") or {})
        if capture.get("type") not in CAPTURE_TYPES:
            raise ValueError(f"screenshots: {name}: capture type must be one of {', '.join(CAPTURE_TYPES)}")
        return cls(
            name=name,
            # `name:<library>` matches the name the library is imported with (normalised)
            match=tuple(
                f"name:{normalize(m[5:])}" if m.lower().startswith("name:") else m for m in data.get("match") or ()
            ),
            capture=capture,
            exclude=tuple(normalize(p) for p in data.get("exclude") or ()),
            exclude_tags=frozenset(t.lower() for t in data.get("exclude_tags") or ()),
            aliases=tuple(data.get("aliases") or ()),
            tested=data.get("tested"),
        )

    def excluded(self, keyword: str, tags: list[str] | tuple[str, ...]) -> bool:
        name = normalize(keyword)
        if any(fnmatch.fnmatchcase(name, pattern) for pattern in self.exclude):
            return True
        return any(tag.lower() in self.exclude_tags for tag in tags)


def load_presets() -> dict[str, Preset]:
    text = resources.files(__package__).joinpath("presets.json").read_text(encoding="utf-8")
    data = json.loads(text)
    return {name: Preset.from_dict(name, entry) for name, entry in data["libraries"].items()}


@dataclass
class Config:
    """The settings of one run."""

    mode: str = "off"
    presets: dict[str, Preset] = field(default_factory=dict)  # the switched-on libraries
    catalog: dict[str, Preset] = field(default_factory=dict)  # every preset, custom ones included
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()  # names in `libraries` that match no preset

    @property
    def active(self) -> bool:
        return self.mode != "off" and (bool(self.presets) or bool(self.include))

    def user_excluded(self, owner: str, keyword: str) -> bool:
        return _matches(self.exclude, owner, keyword)

    def user_included(self, owner: str, keyword: str) -> bool:
        return _matches(self.include, owner, keyword)


def _matches(patterns: tuple[str, ...], owner: str, keyword: str) -> bool:
    """A pattern with a dot is matched against `Owner.Keyword`, one without against the keyword name."""
    name = normalize(keyword)
    full = f"{normalize(owner)}.{name}"
    return any(fnmatch.fnmatchcase(full if "." in p else name, p) for p in patterns)


def build_config(option: str, libraries: str | None = None) -> Config:
    """The settings from the listener's ``screenshots`` (a mode or a JSON file) and ``screenshot_libraries``."""
    value = (option or "off").strip()
    if value.lower() in MODES:
        data: dict[str, Any] = {"mode": value.lower()}
    else:
        path = Path(value)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ValueError(f"screenshots must be one of {', '.join(MODES)} or a JSON file: {e}") from e
        version = data.get("version", CONFIG_VERSION)
        if version != CONFIG_VERSION:
            raise ValueError(
                f"screenshots: {path} has version {version}, this robotframework-events reads {CONFIG_VERSION}"
            )
    if libraries:
        data["libraries"] = [*data.get("libraries", []), *(n.strip() for n in libraries.split(",") if n.strip())]
    return config_from_dict(data)


def config_from_dict(data: dict[str, Any]) -> Config:
    mode = str(data.get("mode", "actions")).lower()
    if mode not in MODES:
        raise ValueError(f"screenshots mode must be one of {', '.join(MODES)}, not {mode!r}")
    presets = load_presets()
    for name, entry in (data.get("custom") or {}).items():
        presets[name] = Preset.from_dict(name, entry)
    # a preset's own name wins over another preset's alias
    by_name = {normalize(preset.name): preset for preset in presets.values()}
    for preset in presets.values():
        for alias in preset.aliases:
            by_name.setdefault(normalize(alias), preset)
    chosen: dict[str, Preset] = {}
    unknown: list[str] = []
    for name in data.get("libraries") or ():
        found = by_name.get(normalize(name))
        if found is None:
            unknown.append(name)
        else:
            chosen[found.name] = found
    return Config(
        mode=mode,
        presets=chosen,
        catalog=presets,
        include=tuple(normalize(p) for p in data.get("include") or ()),
        exclude=tuple(normalize(p) for p in data.get("exclude") or ()),
        unknown=tuple(unknown),
    )
