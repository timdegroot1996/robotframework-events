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
            return candidate
    # a library that adds its own extension
    written = sorted(base.parent.glob(base.name + ".*"))
    return written[0] if written else None


# --- the screen or a window (desktop libraries) ------------------------------------------------


def screen(base: Path, region: str = "screen") -> Path | None:
    """The whole screen, or the part of it where the window in front is (`window`, Windows only; elsewhere the
    screen). The screen's pixels, not the window's own drawing, so windows drawn by the GPU are not blank.
    Needs Pillow (`pip install robotframework-events[screen]`) and a display."""
    try:
        from PIL import ImageGrab
    except ImportError as e:
        raise ApiMismatch("screen capture needs Pillow: pip install robotframework-events[screen]") from e
    box = _foreground_box() if region == "window" and sys.platform == "win32" else None
    image = ImageGrab.grab(bbox=box, all_screens=box is not None)
    path = base.with_suffix(".jpeg")
    image.convert("RGB").save(path, "JPEG", quality=JPEG_QUALITY)
    return path


def _foreground_box() -> tuple[int, int, int, int] | None:
    """The screen rectangle of the window in front, in physical pixels (what ImageGrab uses), without the
    invisible resize border; None when there is no usable window."""
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
            if dwmapi.DwmGetWindowAttribute(window, 9, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:  # 9: frame bounds
                user32.GetWindowRect(window, ctypes.byref(rect))
            # ImageGrab with all_screens counts from the left-top of the virtual screen
            left = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
            top = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
        finally:
            if previous:
                user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(previous))
        if rect.right - rect.left < 10 or rect.bottom - rect.top < 10:
            return None
        return (rect.left - left, rect.top - top, rect.right - left, rect.bottom - top)
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
    return path if path.is_file() else screen(base, "window")


# --- images -------------------------------------------------------------------------------------


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
