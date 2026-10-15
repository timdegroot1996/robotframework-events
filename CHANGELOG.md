# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.7.0](https://github.com/timdegroot1996/robotframework-events/releases/tag/v0.7.0) - 2026-10-16

### Changed
- Lower listener overhead: on the worst case (a loop of `No Operation`) a run takes 11-13% longer with the listener on Python 3.11-3.14 (was 18-24%) and 18-22% on Python 3.10 (was 34-35%). Keyword and loop iteration steps are written without building an event dict when no callback is registered
- Times in step events are written with a fixed number of decimals, so they can end in zeros (`"elapsed":0.0010`, `"t":1791930982.400`). The values are the same; only programs that compare the text see a difference

---

## [0.6.0](https://github.com/timdegroot1996/robotframework-events/releases/tag/v0.6.0) - 2026-10-13

### Added
- Step screenshots for a Playwright-like playback of each test: listener arguments `screenshots` (`off`, `actions`, `all`, `failure`, or a JSON settings file) and `screenshot_libraries`. Libraries are opt-in (none gets screenshots until it is named), keywords opt-out (read-only keywords are excluded per library). Presets for 22 libraries, among them Browser, SeleniumLibrary, AppiumLibrary, QWeb, RPA Framework, FlaUI, WhiteLibrary and PlatynUI; libraries built on one (Zoomba, `RPA.Browser.*`) are recognised. The README lists them and the versions they were tested with
- `step.screenshot` and `screenshot.unavailable` events (format v1, new event types): the file of a step's screenshot, and why a library's screenshots were switched off (dialog open, timeouts, an API that changed), so viewers can show it and users can report it
- `screenshot` on steps in `RunState`
- Optional extra `screen` (Pillow): screenshots of the screen or the window in front for desktop libraries, and JPEG instead of PNG for the other screenshots (about eight times smaller)
- `rfevents rebuild` and `rebuild()`: a Robot Framework `output.xml` from the events of a run that crashed before writing it. What did not finish fails, like Robot Framework would have failed it

---

## [0.5.0](https://github.com/timdegroot1996/robotframework-events/releases/tag/v0.5.0) - 2026-10-12

### Added
- `flush` listener argument (default `0.1` seconds): the events file is flushed regularly while the run goes on, so `rfevents tail -f` and editors that follow the file see the keyword that is running, not only finished tests. `flush=0` keeps the old behaviour (flushed after every test)
- `pabot` in `run.started` (format v1, new optional field): for one item of a pabot run, its queue index, executor pool id, number of processes and whether it is the last item pabot starts, so viewers can merge the items of one pabot run

### Changed
- The events file is written with LF line endings on every operating system (it used CRLF on Windows)

---

## [0.4.0](https://github.com/timdegroot1996/robotframework-events/releases/tag/v0.4.0) - 2026-10-11

### Added
- `planned` in the top-level `suite.started` (also in converted events): the full names of every test the run will execute, in run order, so viewers can estimate the remaining time from the tests that were actually selected

---

## [0.3.0](https://github.com/timdegroot1996/robotframework-events/releases/tag/v0.3.0) - 2026-10-11

### Added
- `outputdir` in `run.started` (also in events converted from an output file): the run's output directory, so viewers can show screenshots and other files that log messages link relative to it

---

## [0.2.0](https://github.com/timdegroot1996/robotframework-events/releases/tag/v0.2.0) - 2026-10-10

### Changed
- The default events file is named after the output file, the way robotdashboard finds a run's `log.html`: `output.xml` gives `events.jsonl`, `output-20261010.xml` gives `events-20261010.jsonl`, next to the output file, so robotframework-dashboard can replay runs written with `--output output-XYZ.xml`. With `--output NONE` it stays `${OUTPUT DIR}/events.jsonl`

---

## [0.1.0](https://github.com/timdegroot1996/robotframework-events/releases/tag/v0.1.0) - 2026-10-10

First release.

### Added
- `robotframework_events.Listener` — a Robot Framework listener that writes every suite, test, keyword, control structure (FOR, ITERATION, IF, TRY, WHILE, GROUP, VAR, ...) and log message of a run as JSON Lines while the run happens. Item ids are Robot Framework's own (`s1-t2-k3`), so events join with `output.xml` and link into `log.html#<id>`. Options: `file`, `level`, `messages`, `args`, `structures` and `max_text`
- Event format v1 with a JSON Schema (`events-v1.schema.json`, also `robotframework_events.schema()`) and typed event classes for readers (`robotframework_events.events`, `from_dict`)
- `status.changed` events for suites and tests whose status or message a failing suite teardown changes after they ended
- `add_callback` for programs that run Robot Framework in the same process, such as robotcode's debugger
- `read_events` for `.jsonl` and `.jsonl.gz` files, with a follow mode for files that are still being written
- `RunState` — the tree of suites, tests and steps with status, messages and times, built from events
- `convert` — events from an existing `output.xml` or `output.json`, for runs recorded without the listener
- The `rfevents` command: `rfevents tail [-f]` shows a run in the terminal keyword by keyword, `rfevents convert` writes events for a result file
- Supports Robot Framework 7.0 and newer on Python 3.10 to 3.14
