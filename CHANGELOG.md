# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
