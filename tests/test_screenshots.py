"""Step screenshots (listener options screenshots and screenshot_libraries), with fake libraries:
FakeBrowser has a WebDriver-like driver, FakeAngular works on FakeBrowser's page."""

import json

import pytest
from robot.api import ExecutionResult

from conftest import DATA, run_with_listener
from robotframework_events import RunState, from_dict
from robotframework_events.listener import Listener
from robotframework_events.screenshots import build_config, config_from_dict, load_presets, normalize

FAKE = {
    "Fake": {
        "match": ["FakeBrowser:FakeBrowser"],
        "capture": {"type": "webdriver", "driver": "driver"},
        "exclude": ["Get *", "*Should*", "Handle Alert"],
    },
    "FakeAngular": {
        "match": ["FakeBrowser:FakeAngular"],
        "capture": {"type": "borrow", "from": ["Fake"]},
        "exclude": ["Wait For Angular"],
    },
}


@pytest.fixture(autouse=True)
def fake_libraries(monkeypatch):
    monkeypatch.syspath_prepend(str(DATA))


def settings(tmp_path, **fields):
    """A screenshots settings file with the fake libraries switched on."""
    data = {"version": 1, "mode": "actions", "libraries": ["Fake", "FakeAngular"], "custom": FAKE, **fields}
    path = tmp_path / "screenshots.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path).replace("\\", "/")


def run(tmp_path, test, **fields):
    return run_with_listener(
        tmp_path, [DATA / "screenshots.robot"], f"screenshots={settings(tmp_path, **fields)}", test=test
    )


def shots(events):
    names = {e["id"]: e.get("name") for e in events if e["type"] == "step.started"}
    return [names[e["id"]] for e in events if e["type"] == "step.screenshot"]


def unavailable(events):
    return [(e.get("library"), e["reason"]) for e in events if e["type"] == "screenshot.unavailable"]


# --- which keywords ------------------------------------------------------------------------------


def test_every_keyword_of_a_switched_on_library_except_the_excluded_ones(tmp_path):
    events, output = run(tmp_path, "Steps With A Page")
    # Open Page has a page once it ran; Get and Should keywords are excluded; failures always
    assert shots(events) == ["Open Page", "Click", "Click"]
    first = next(e for e in events if e["type"] == "step.screenshot")
    assert first["library"] == "Fake"
    assert (tmp_path / first["path"]).is_file()
    assert first["path"].startswith("rfevents-screenshots/00001.")
    # each follows its step's step.ended
    for index, event in enumerate(events):
        if event["type"] == "step.screenshot":
            assert events[index - 1]["type"] == "step.ended"
            assert events[index - 1]["id"] == event["id"]
    # nothing in output.xml
    test = ExecutionResult(str(output)).suite.tests[0]
    messages = [m.message for kw in test.body for m in kw.body if getattr(m, "type", "") == "MESSAGE"]
    assert messages == ["element missing not found"]
    state = RunState.from_events(from_dict(e) for e in events)
    path = next(e["path"] for e in events if e["type"] == "step.screenshot" and e["id"] == "s1-t1-k2")
    assert state.nodes["s1-t1-k2"].screenshot == path


@pytest.mark.parametrize(("mode", "count"), [("all", 5), ("failure", 1), ("off", 0)])
def test_modes(tmp_path, mode, count):
    events, _ = run(tmp_path, "Steps With A Page", mode=mode)
    assert len(shots(events)) == count


def test_keywords_the_user_excludes(tmp_path):
    events, _ = run(tmp_path, "Steps With A Page", exclude=["FakeBrowser.Open Page", "click"])
    # failures always get one
    assert shots(events) == ["Click"]


def test_keywords_that_do_not_run_get_no_screenshot(tmp_path):
    events, _ = run(tmp_path, "Keywords That Do Not Run", mode="all")
    args = {e["id"]: e.get("args") for e in events if e["type"] == "step.started"}
    assert [args[e["id"]] for e in events if e["type"] == "step.screenshot"] == [None, ["button"]]


def test_own_keywords_and_libraries_that_borrow_a_page(tmp_path):
    events, _ = run(tmp_path, "Own Keyword And Borrowed Page", include=["Log In"])
    # Log In (own keyword) uses the page of the last screenshot; FakeAngular borrows FakeBrowser's page
    assert shots(events) == ["Open Page", "Click", "Click", "Log In", "Click Angular Button"]
    borrowed = [e for e in events if e["type"] == "step.screenshot"][-1]
    assert borrowed["library"] == "FakeAngular"


# --- opt-in --------------------------------------------------------------------------------------


def test_no_library_gets_screenshots_until_it_is_named(tmp_path):
    events, _ = run_with_listener(
        tmp_path, [DATA / "screenshots.robot"], "screenshots=actions", test="Steps With A Page"
    )
    assert shots(events) == []
    assert unavailable(events) == [
        (None, "screenshots are on, but no library is named (screenshot_libraries=Browser,...)")
    ]
    assert events[0]["type"] == "run.started"


def test_libraries_named_in_the_listener_arguments(tmp_path, capfd):
    events, _ = run_with_listener(
        tmp_path,
        [DATA / "screenshots.robot"],
        "screenshots=actions;screenshot_libraries=SeleniumLibrary, NoSuchLibrary",
        test="Steps With A Page",
    )
    # SeleniumLibrary is not used by this suite; an unknown name is reported
    assert shots(events) == []
    [(library, reason)] = unavailable(events)
    assert library == "NoSuchLibrary"
    assert reason == "no preset with this name; add it under `custom` to switch it on"
    assert "no step screenshots with NoSuchLibrary" in capfd.readouterr().err


# --- guards --------------------------------------------------------------------------------------


def test_no_screenshot_while_a_dialog_is_open(tmp_path):
    events, output = run(tmp_path, "Dialog Stays Open")
    # not Open Dialog's and Click's (a dialog is open), and the test could still handle it
    assert shots(events) == ["Open Page"]
    assert ExecutionResult(str(output)).suite.tests[0].status == "PASS"


def test_a_library_whose_screenshots_time_out_is_turned_off(tmp_path, capfd):
    events, _ = run(tmp_path, "Slow Screenshots Turn The Library Off")
    assert shots(events) == ["Open Page"]
    assert unavailable(events) == [("Fake", "3 screenshots in a row timed out")]
    assert "no step screenshots with Fake" in capfd.readouterr().err


def test_a_library_whose_api_does_not_fit_is_turned_off(tmp_path):
    events, output = run(tmp_path, "Broken API Turns The Library Off")
    assert shots(events) == ["Open Page"]
    [(library, reason)] = unavailable(events)
    assert library == "Fake"
    assert reason.startswith("its API does not fit (TypeError")
    assert ExecutionResult(str(output)).suite.tests[0].status == "PASS"


# --- settings ------------------------------------------------------------------------------------


def test_every_preset_is_valid():
    presets = load_presets()
    assert {"Browser", "SeleniumLibrary", "AppiumLibrary", "FlaUI", "SapGuiLibrary", "WhiteLibrary"} <= set(presets)
    for preset in presets.values():
        assert preset.match, preset.name


def test_libraries_are_switched_on_by_name_or_alias():
    config = config_from_dict({"libraries": ["rpa.browser.selenium", "Browser", "Nope"]})
    assert sorted(config.presets) == ["Browser", "SeleniumLibrary"]
    assert config.unknown == ("Nope",)


def test_a_preset_name_wins_over_an_alias():
    config = config_from_dict(
        {
            "libraries": ["RemoteSwingLibrary"],
            "custom": {"Other": {"match": ["x:Y"], "capture": {"type": "screen"}, "aliases": ["RemoteSwingLibrary"]}},
        }
    )
    assert list(config.presets) == ["RemoteSwingLibrary"]


def test_browser_keywords_are_excluded_by_tag():
    browser = load_presets()["Browser"]
    assert not browser.excluded("Click", ["Setter", "PageContent"])
    assert not browser.excluded("New Page", ["Setter", "BrowserControl"])
    assert browser.excluded("Get Text", ["Getter", "Assertion", "PageContent"])
    assert browser.excluded("Some New Waiting Keyword", ["Wait"])


def test_names_are_compared_like_keywords():
    assert normalize("Get_Text") == normalize("get  text") == "get text"
    selenium = load_presets()["SeleniumLibrary"]
    assert selenium.excluded("Log Source", [])
    assert not selenium.excluded("Login To Shop", [])


def test_wrong_settings_are_errors(tmp_path):
    with pytest.raises(ValueError, match="screenshots mode must be one of"):
        config_from_dict({"mode": "sometimes"})
    newer = tmp_path / "newer.json"
    newer.write_text(json.dumps({"version": 2}), encoding="utf-8")
    with pytest.raises(ValueError, match="has version 2"):
        build_config(str(newer))
    with pytest.raises(ValueError, match="or a JSON file"):
        Listener(screenshots="sometimes")


# --- adapters without a library to run here ------------------------------------------------------


class _SapWindow:
    def __init__(self, fail: bool) -> None:
        self.fail = fail

    def HardCopy(self, path: str, image_type: int) -> str:
        if self.fail:
            raise RuntimeError("scripting disabled")
        assert image_type == 2  # PNG
        with open(path, "wb") as file:
            file.write(b"PNG fake")
        return path


class _SapSession:
    def __init__(self, fail: bool = False) -> None:
        self.window = _SapWindow(fail)

    def findById(self, element: str) -> _SapWindow:
        assert element == "wnd[0]"
        return self.window


class _SapGuiLibrary:
    def __init__(self, session: object) -> None:
        self.session = session


def test_sap_gui_window_hard_copy(tmp_path, monkeypatch):
    from robotframework_events.screenshots import adapters

    # connected: the SAP window itself
    path = adapters.sapgui(_SapGuiLibrary(_SapSession()), tmp_path / "00001")
    assert path == tmp_path / "00001.png" and path.is_file()
    # not connected yet (SapGuiLibrary keeps -1): no screenshot
    assert adapters.sapgui(_SapGuiLibrary(-1), tmp_path / "00002") is None
    # scripting refuses: the window in front instead
    monkeypatch.setattr(adapters, "screen", lambda base, region: base.with_suffix(".jpeg"))
    assert adapters.sapgui(_SapGuiLibrary(_SapSession(fail=True)), tmp_path / "00003") == tmp_path / "00003.jpeg"
