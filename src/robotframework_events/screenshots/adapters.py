"""How a screenshot is taken, per kind of library (``capture.type`` in the presets).

Each adapter gets the library instance and a file path without extension, and returns the image file it
wrote, or None when there is nothing to capture (no browser or page open, a dialog open, no window).
:class:`ApiMismatch` (or a TypeError, AttributeError, ImportError) means the library's API is not what the
adapter expects; the library is then left alone for the rest of the run.
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

TIMEOUT = timedelta(seconds=2)
JPEG_QUALITY = 70


class ApiMismatch(Exception):
    pass


def capture(spec: dict[str, Any], instance: Any, base: Path, borrow: Callable[[list[str]], Path | None]) -> Path | None:
    kind = spec["type"]
    if kind == "browser":
        return browser(instance, base)
    if kind == "webdriver":
        return webdriver(_driver(instance, spec.get("driver", "driver")), base)
    if kind == "qweb":
        return webdriver(_qweb_driver(), base)
    if kind == "method":
        return method(instance, spec["method"], base, spec.get("extension", ".png"))
    if kind == "screen":
        return screen(base, spec.get("region", "screen"))
    if kind == "sapgui":
        return sapgui(instance, base)
    if kind == "borrow":
        return borrow(list(spec.get("from") or []))
    raise ApiMismatch(f"unknown capture type {kind!r}")


# --- Browser (Playwright) -----------------------------------------------------------------------

_browser_args: dict[int, dict[str, Any]] = {}


def browser(instance: Any, base: Path) -> Path | None:
    key = id(type(instance))
    if key not in _browser_args:
        _browser_args[key] = _browser_screenshot_args(instance)
    result = instance.take_screenshot(str(base), **_browser_args[key])
    if isinstance(result, Path):
        return result
    return Path(result) if isinstance(result, str) and result.upper() != "EMBED" else None


def _browser_screenshot_args(instance: Any) -> dict[str, Any]:
    """The keyword arguments of Browser's take_screenshot that this version has: JPEG, not logged, a short
    timeout, the path back. Its first argument (the file name) is all that is required."""
    try:
        parameters = inspect.signature(instance.take_screenshot).parameters
    except (TypeError, ValueError) as e:
        raise ApiMismatch(f"take_screenshot: {e}") from e
    if "filename" not in parameters:
        raise ApiMismatch("take_screenshot has no filename argument")
    args: dict[str, Any] = {}
    if "log_screenshot" in parameters:
        args["log_screenshot"] = False
    if "timeout" in parameters:
        args["timeout"] = TIMEOUT
    try:
        from Browser.utils.data_types import (  # type: ignore[import-untyped,import-not-found,unused-ignore]
            ScreenshotFileTypes,
            ScreenshotReturnType,
        )
    except ImportError:
        return args
    if "fileType" in parameters and hasattr(ScreenshotFileTypes, "jpeg"):
        args["fileType"] = ScreenshotFileTypes.jpeg
        if "quality" in parameters:
            args["quality"] = JPEG_QUALITY
    if "return_as" in parameters and hasattr(ScreenshotReturnType, "path_string"):
        args["return_as"] = ScreenshotReturnType.path_string
    return args


# --- WebDriver (SeleniumLibrary, AppiumLibrary, QWeb) ----------------------------------------------


def _driver(instance: Any, accessor: str) -> Any:
    """The WebDriver of a library: an attribute (`driver`) or a method without arguments (`_current_application()`);
    None when no browser or application is open."""
    name = accessor.removesuffix("()")
    if not hasattr(type(instance), name) and not hasattr(instance, name):
        raise ApiMismatch(f"no {accessor}")
    try:
        value = getattr(instance, name)
        return value() if accessor.endswith("()") else value
    except Exception:
        return None  # no browser or application open


def _qweb_driver() -> Any:
    from QWeb.internal import browser as qweb_browser  # type: ignore[import-untyped,import-not-found,unused-ignore]

    try:
        return qweb_browser.get_current_browser()
    except Exception:
        return None


def webdriver(driver: Any, base: Path) -> Path | None:
    """A WebDriver screenshot, unless a JavaScript dialog is open: WebDriver would dismiss it (the default
    unhandled prompt behaviour) and the test could not handle it anymore. In a native mobile app (Appium,
    context NATIVE_APP) there are no such dialogs and the check is not supported."""
    if driver is None:
        return None
    if not _native(driver):
        try:
            driver.switch_to.alert.text  # noqa: B018 reading the text leaves the dialog open
        except Exception as e:
            if type(e).__name__ != "NoAlertPresentException":
                return None  # cannot tell: better no screenshot
        else:
            return None
    png = driver.get_screenshot_as_png()
    return _save_image(png, base)


def _native(driver: Any) -> bool:
    try:
        context = driver.current_context
    except Exception:
        return False
    return isinstance(context, str) and context.upper().startswith("NATIVE")


# --- the library's own screenshot method ------------------------------------------------------


def method(instance: Any, name: str, base: Path, extension: str) -> Path | None:
    """Calls the library's screenshot method with a file path (positionally: argument names differ between
    versions and languages) and returns the file it wrote."""
    function = getattr(instance, name, None)
    if function is None:
        raise ApiMismatch(f"no method {name}")
    target = base.with_suffix(extension)
    result = function(str(target))
    for candidate in (target, Path(result) if isinstance(result, str) else None):
        if candidate is not None and candidate.is_file():
            return _as_jpeg(candidate)
    # a library that adds its own extension
    written = sorted(base.parent.glob(base.name + ".*"))
    return _as_jpeg(written[0]) if written else None


# --- the screen or a window (desktop libraries) ------------------------------------------------


def screen(base: Path, region: str = "screen") -> Path | None:
    """The screen, or the part of it where the window in front is (`window`). On Windows "the screen" is the
    monitor the window in front is on (with several monitors); elsewhere the main screen. The screen's pixels,
    not the window's own drawing, so windows drawn by the GPU are not blank.
    Needs Pillow (`pip install robotframework-events[screen]`) and a display."""
    try:
        from PIL import ImageGrab
    except ImportError as e:
        raise ApiMismatch("screen capture needs Pillow: pip install robotframework-events[screen]") from e
    box = _foreground_box(monitor=region != "window") if sys.platform == "win32" else None
    image = ImageGrab.grab(bbox=box, all_screens=box is not None)
    path = base.with_suffix(".jpeg")
    image.convert("RGB").save(path, "JPEG", quality=JPEG_QUALITY)
    return path


def _foreground_box(monitor: bool = False) -> tuple[int, int, int, int] | None:
    """The screen rectangle of the window in front (or, with `monitor`, of the monitor it is on), in physical
    pixels of the virtual screen, as ImageGrab's bbox takes them (it subtracts the virtual screen's origin
    itself, which is negative when a monitor is left of or above the main one). Without the window's invisible
    resize border; None when there is no usable window."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined,unused-ignore]
        dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined,unused-ignore]
        # physical pixels: per-monitor DPI aware while asking
        previous = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        try:
            window = user32.GetForegroundWindow()
            if not window or user32.IsIconic(window):
                return None
            rect = wintypes.RECT()
            if monitor:

                class MonitorInfo(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD),
                    ]

                user32.MonitorFromWindow.restype = wintypes.HANDLE
                handle = user32.MonitorFromWindow(window, 2)  # MONITOR_DEFAULTTONEAREST
                info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
                if not handle or not user32.GetMonitorInfoW(wintypes.HANDLE(handle), ctypes.byref(info)):
                    return None
                rect = info.rcMonitor
            elif dwmapi.DwmGetWindowAttribute(window, 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:  # frame bounds
                user32.GetWindowRect(window, ctypes.byref(rect))
            # a window can stick out of the screen: only the part on it
            left, top = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)  # SM_X/YVIRTUALSCREEN
            right, bottom = left + user32.GetSystemMetrics(78), top + user32.GetSystemMetrics(79)  # width, height
        finally:
            if previous:
                user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(previous))
        box = (max(rect.left, left), max(rect.top, top), min(rect.right, right), min(rect.bottom, bottom))
        if box[2] - box[0] < 10 or box[3] - box[1] < 10:
            return None
        return box
    except Exception:
        return None


# --- SAP GUI (SapGuiLibrary, RPA.SAP) ---------------------------------------------------------


def sapgui(instance: Any, base: Path) -> Path | None:
    """The SAP GUI window through SAP GUI Scripting (``HardCopy`` of the main window), else the window in front.
    SapGuiLibrary keeps -1 as its session until it is connected."""
    session = getattr(instance, "session", None)
    if session is None or isinstance(session, int):
        return None
    path = base.with_suffix(".png")
    try:
        session.findById("wnd[0]").HardCopy(str(path), 2)  # 2: PNG
    except Exception:
        return screen(base, "window")
    return _as_jpeg(path) if path.is_file() else screen(base, "window")


# --- images -------------------------------------------------------------------------------------


def _as_jpeg(path: Path) -> Path:
    """A PNG or BMP a library wrote, as JPEG when Pillow is there (a phone screen: 1.3 MB as PNG, about 150 KB
    as JPEG); the file as it is otherwise, or when Pillow cannot read it."""
    if path.suffix.lower() not in (".png", ".bmp"):
        return path
    try:
        from PIL import Image

        target = path.with_suffix(".jpeg")
        with Image.open(path) as image:
            image.convert("RGB").save(target, "JPEG", quality=JPEG_QUALITY)
    except Exception:
        return path
    path.unlink(missing_ok=True)
    return target


def _save_image(png: bytes, base: Path) -> Path:
    """JPEG when Pillow is there (about eight times smaller), else the PNG as it came."""
    try:
        import io

        from PIL import Image

        path = base.with_suffix(".jpeg")
        Image.open(io.BytesIO(png)).convert("RGB").save(path, "JPEG", quality=JPEG_QUALITY)
        return path
    except ImportError:
        path = base.with_suffix(".png")
        path.write_bytes(png)
        return path
