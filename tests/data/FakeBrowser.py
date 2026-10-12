"""A library with a WebDriver-like driver for the screenshots option (see test_screenshots.py)."""

import struct
import time
import zlib

from robot.api import logger


def _png() -> bytes:
    """A real 1x1 PNG, so the adapter can convert it."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\xff\x00\x00")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


class NoAlertPresentException(Exception):  # named like Selenium's
    pass


class _Alert:
    def __init__(self, driver: "_Driver") -> None:
        self._driver = driver

    @property
    def text(self) -> str:
        if self._driver.dialog is None:
            raise NoAlertPresentException
        return self._driver.dialog


class _SwitchTo:
    def __init__(self, driver: "_Driver") -> None:
        self.alert = _Alert(driver)


class _Driver:
    def __init__(self) -> None:
        self.dialog: str | None = None
        self.switch_to = _SwitchTo(self)
        self.mode = "ok"  # ok, slow, broken

    def get_screenshot_as_png(self) -> bytes:
        if self.dialog is not None:
            # what WebDriver does with an open dialog by default
            self.dialog = None
            raise RuntimeError("unexpected alert open: dismissed")
        if self.mode == "slow":
            time.sleep(1.6)
            raise RuntimeError("timeout")
        if self.mode == "broken":
            raise TypeError("get_screenshot_as_png() got an unexpected keyword argument")
        logger.info("took a screenshot")  # must not reach the log
        return _png()


class FakeBrowser:
    def __init__(self) -> None:
        self._driver: _Driver | None = None

    @property
    def driver(self) -> _Driver:
        if self._driver is None:
            raise RuntimeError("no browser open")
        return self._driver

    def open_page(self) -> None:
        self._driver = _Driver()

    def click(self, locator: str) -> None:
        if locator == "missing":
            raise AssertionError(f"element {locator} not found")

    def open_dialog(self) -> None:
        self.driver.dialog = "sure?"

    def handle_alert(self) -> None:
        if self.driver.dialog is None:
            raise AssertionError("Alert not found")
        self.driver.dialog = None

    def make_screenshots(self, mode: str) -> None:
        self.driver.mode = mode

    def get_title(self) -> str:
        return "title"

    def element_should_be_visible(self, locator: str) -> None:
        pass


class FakeAngular:
    """Works on FakeBrowser's page, like AngularJSLibrary on SeleniumLibrary's."""

    def wait_for_angular(self) -> None:
        pass

    def click_angular_button(self) -> None:
        pass
