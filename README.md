# robotframework-events

A Robot Framework listener that writes every suite, test, keyword, control structure and log
message of a run as JSON Lines, while the run happens. Item ids are Robot Framework's own
(`s1-t2-k3`), so events join with `output.xml` and link into `log.html#<id>`.

Requires Robot Framework 7.0 or newer and Python 3.10 or newer. Status: alpha.

```
pip install robotframework-events
robot --listener robotframework_events.Listener tests/                       # writes events.jsonl next to output.xml
robot --listener "robotframework_events.Listener;file=ev.jsonl;level=DEBUG" tests/
```

Listener arguments: `file` (`NONE` for no file), `level` (minimum message level, default `INFO`),
`messages`, `args`, `structures` (each `true`/`false`, default `true`), `max_text` (default 4096) and
`flush` (seconds between flushes of the file while the run goes on, default 0.1, so `rfevents tail -f` and
editors that follow the file see the keyword that is running; `0` flushes after every test only).

## Step screenshots

With `screenshots`, the listener takes a screenshot after the keywords of the libraries you name, for a
Playwright-like playback of each test (robotframework-dashboard's Live page). Libraries are opt-in, keywords
opt-out: in a named library every keyword gets one, except the read-only ones its preset excludes
(`Get ...`, `Wait ...`, `... Should ...` and similar); failing keywords always get one.

```
pip install "robotframework-events[screen]"     # Pillow: desktop libraries, and JPEG instead of PNG
robot --listener "robotframework_events.Listener;screenshots=actions;screenshot_libraries=Browser,SeleniumLibrary" tests/
```

`screenshots` is `off` (default), `actions`, `all` (every keyword, exclusions ignored) or `failure`, or the
path of a JSON file with more settings:

```json
{
  "version": 1,
  "mode": "actions",
  "libraries": ["Browser", "FlaUI"],
  "include": ["MyShop.Log In"],
  "exclude": ["Browser.Hover", "Scroll To *"],
  "custom": {
    "MyDesktopLibrary": {"match": ["mydesktop:MyDesktopLibrary"], "capture": {"type": "screen", "region": "window"}}
  }
}
```

`include` adds own keywords (from resource files); they show the page of the library used last. `custom`
adds a library without a preset: `match` names its class (`topmodule:Class`, base classes count) or the
name it is imported with (`name:JavaFXLibrary`), `capture.type` is `browser`, `webdriver` (with `driver`:
`driver` or `_current_application()`), `borrow` (with `from`: the libraries whose page it works on), `method`
(with `method`: the library's screenshot method, called with a file path) or `screen` (with `region`:
`screen` or `window`, the window in front). The presets are in
[`presets.json`](src/robotframework_events/screenshots/presets.json).

The images go to `${OUTPUT DIR}/rfevents-screenshots/`, each announced with a `step.screenshot` event after
its `step.ended`. They are taken through the library directly, so nothing is added to `output.xml` or
`log.html`. Each one takes time, so they are off by default.

Libraries change fast, so a screenshot never gets in the way of a test: none is taken while a JavaScript
dialog is open (WebDriver would dismiss it), Browser's `Take Screenshot` arguments are read from its
signature, and a library whose API does not fit or whose screenshots keep timing out is left alone for the
rest of the run. That is reported on the console and as a `screenshot.unavailable` event, which the Live page
shows: please [report it](https://github.com/timdegroot1996/robotframework-events/issues) with the
library's version.

### Supported libraries

Every library from [awesome-robotframework](https://github.com/MarketSquare/awesome-robotframework) that can
take a screenshot. "Tested" means a test run with and without screenshots gave the same results, with real
screenshots, on Windows 10 (Android 14 emulator for the mobile libraries). Browser, SeleniumLibrary, QWeb, AppiumLibrary,
RPA Framework (`RPA.Browser.*`, `RPA.Windows`), WhiteLibrary, Puppeteer Library and FlaUI are checked again every week,
with the versions in the table and with their latest releases. Problems with a library: open a
[step screenshots issue](https://github.com/timdegroot1996/robotframework-events/issues/new?template=step-screenshots.yml).

| Library | Name in `screenshot_libraries` | Screenshot of | Tested with |
|---|---|---|---|
| [Browser](https://github.com/MarketSquare/robotframework-browser) | `Browser` | the page | 20.6.0 |
| [SeleniumLibrary](https://github.com/robotframework/SeleniumLibrary) | `SeleniumLibrary` | the page | 6.9.0 |
| [AppiumLibrary](https://github.com/serhatbolsu/robotframework-appiumlibrary) | `AppiumLibrary` | the app or page | 3.2.1 (native app and Chrome) |
| [RPA Framework](https://github.com/robocorp/rpaframework) `RPA.Browser.Selenium` | `RPA.Browser.Selenium` | the page | rpaframework 33.0.2 |
| RPA Framework `RPA.Browser.Playwright` | `RPA.Browser.Playwright` | the page | rpaframework 33.0.2 |
| RPA Framework `RPA.Desktop` | `RPA.Desktop` | the screen | rpaframework 33.0.2 |
| RPA Framework `RPA.Windows` | `RPA.Windows` | the window in front | rpaframework-windows 11.0.0 |
| [QWeb](https://github.com/qentinelqi/qweb) | `QWeb` | the page | 3.8.3 |
| [WhiteLibrary](https://github.com/Omenia/robotframework-whitelibrary) | `WhiteLibrary` | the window in front | 1.6.0 (needs Python 3.10 or older) |
| [Puppeteer Library](https://github.com/qahive/robotframework-puppeteer) | `PuppeteerLibrary` | the page | 3.1.10 (needs Python 3.10 or older) |
| [FlaUI](https://github.com/GDATASoftwareAG/robotframework-flaui) | `FlaUI` | the window in front | 5.2.1 |
| [Zoomba](https://github.com/Accruent/robotframework-zoomba) `GUILibrary` | `Zoomba.GUILibrary` | the page | 4.6.1 |
| [ApplicationLibrary](https://github.com/Accruent/robotframework-applicationlibrary) `MobileLibrary` (was Zoomba's) | `ApplicationLibrary.MobileLibrary` | the app | 1.2.1 |
| [AngularJS Library](https://github.com/MarketSquare/robotframework-angularjs) | `AngularJSLibrary` with `SeleniumLibrary` | SeleniumLibrary's page | 1.0.0 |
| [SikuliLibrary](https://github.com/rainmanwy/robotframework-SikuliLibrary) | `SikuliLibrary` | the screen | 2.0.6 |
| [ImageHorizonLibrary](https://github.com/eficode/robotframework-imagehorizonlibrary) | `ImageHorizonLibrary` | the screen | 1.0 |
| [Remote Swing Library](https://github.com/robotframework/remoteswinglibrary) | `RemoteSwingLibrary` | the window in front | 2.3.3 |
| [ADB Library](https://pypi.org/project/robotframework-adblibrary/) | `ADBLibrary` | the device screen | 0.1.3 |
| [SapGui Library](https://github.com/frankvanderkuur/robotframework-sapguilibrary), `RPA.SAP` | `SapGuiLibrary`, `RPA.SAP` | the SAP window | not tested (needs a SAP system) |
| [RoboSAPiens](https://github.com/imbus/robotframework-robosapiens) | `RoboSAPiens` | the SAP window | not tested (needs a SAP system) |
| [AutoIt Library](https://github.com/nokia/robotframework-autoitlibrary) | `AutoItLibrary` | the window in front | not tested (needs AutoItX registered) |
| [PlatynUI](https://github.com/imbus/robotframework-PlatynUI) | `PlatynUI` | the window in front | 0.9.2 (needs the .NET 8 runtime; in one run with FlaUI or WhiteLibrary, which start .NET Framework, use it through `Remote ... AS PlatynUI`) |
| [JupyterLibrary](https://github.com/robots-from-jupyter/robotframework-jupyterlibrary) | `JupyterLibrary` with `SeleniumLibrary` | SeleniumLibrary's page | not tested |
| [Swing Library](https://github.com/robotframework/SwingLibrary) | `SwingLibrary` | the window in front | not tested |
| [JavaFXLibrary](https://github.com/eficode/JavaFXLibrary) (through `Remote`) | `JavaFXLibrary` | the window in front | not tested |
| [Eclipse Library](https://github.com/lcarbonn/robotframework-eclipselibrary) | `EclipseLibrary` | the window in front | not tested |

Libraries built on one of these are recognised by their base class. Not supported: Mainframe 3270 (its
screenshot is the terminal's text). "The screen" and "the window in front" need a display, and show what is
visible there, other windows included.

## Event format

One JSON object per line. Every event has `v` (format version), `seq` (1, 2, 3, ...), `t` (Unix
time) and `type`: `run.started`, `suite.started`, `test.started`, `step.started`,
`message.logged`, `step.ended`, `step.screenshot`, `test.ended`, `suite.ended`, `status.changed`,
`resultfile.created`, `run.ended`.

```jsonl
{"v":1,"seq":6,"t":1791581563.542,"type":"test.started","id":"s1-t1","parent":"s1","name":"Passing","longname":"Sample.Passing","lineno":6}
{"v":1,"seq":61,"t":1791581563.601,"type":"test.ended","id":"s1-t2","status":"FAIL","message":"1 != 2","elapsed":0.004}
```

The JSON Schema [`events-v1.schema.json`](src/robotframework_events/events-v1.schema.json) is the
reference.

## Command line

```
rfevents tail -f results/events.jsonl          # follow a run in the terminal, keyword by keyword
rfevents tail --steps 2 --level INFO events.jsonl
rfevents convert output.xml -o events.jsonl    # events for a run recorded without the listener
rfevents rebuild events.jsonl -o output.xml    # output.xml for a run that crashed before writing it
```

`tail` prints suites, tests, steps down to `--steps` levels (default 1), log messages from
`--level` (default `WARN`) and a summary. `convert` reads `output.xml` or `output.json`; steps
then have no source or line number, which result files do not store. `rebuild` is the other way
round, for a run that was killed or crashed: the tests and steps that were still running fail with
"Not finished", tests that never started are left out, and the top-level suite says the run did not
finish.

With pabot, every process writes its own events file in its own output folder
(`pabot --listener robotframework_events.Listener tests/`); `run.started` then has a `pabot` field
with the process's `index`, `pool`, `processes` and whether it is the `last` one pabot starts.

## Python API

```python
from robotframework_events import RunState, add_callback, convert, read_events, rebuild

state = RunState.from_events(read_events("events.jsonl"))  # also .jsonl.gz
print(state.status, state.counts())
for event in read_events("events.jsonl", follow=True):  # while the run writes it
    ...

events = list(convert("output.xml"))  # dicts, as the listener writes them
rebuild(read_events("events.jsonl")).save("output.xml")  # a Robot Framework result
add_callback(fn)  # in-process consumers, e.g. robotcode's debugger
```

`read_events` gives typed events (`robotframework_events.events`). `RunState` holds the tree of
suites, tests and steps with status, messages and times, and the running test and step.

## Development

```
pip install -e .[dev]
ruff check . && ruff format --check . && mypy
pytest                 # format, options, schema, reader, CLI and conformance tests
pytest -m bench        # listener overhead
pytest -m e2e          # through robotcode's debugger (needs ../robotcode)
```

The conformance tests also run on Robot Framework's acceptance test data, found through
`RF_ATEST_DIR` or at `../robotframework/atest/testdata`, and are skipped when it is missing.

## Licence

MIT
