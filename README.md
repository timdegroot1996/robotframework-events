# robotframework-events

A Robot Framework listener that writes every suite, test, keyword, control structure and log
message of a run as JSON Lines, while the run happens. Item ids are Robot Framework's own
(`s1-t2-k3`), so events join with `output.xml` and link into `log.html#<id>`.

Requires Robot Framework 7.5 or newer and Python 3.10 or newer. Status: alpha, not on PyPI yet.

```
pip install -e .
robot --listener robotframework_events.Listener tests/                       # writes ${OUTPUT DIR}/events.jsonl
robot --listener "robotframework_events.Listener;file=ev.jsonl;level=DEBUG" tests/
```

Listener arguments: `file` (`NONE` for no file), `level` (minimum message level, default `INFO`),
`messages`, `args`, `structures` (each `true`/`false`, default `true`) and `max_text` (default 4096).

## Event format

One JSON object per line. Every event has `v` (format version), `seq` (1, 2, 3, ...), `t` (Unix
time) and `type`: `run.started`, `suite.started`, `test.started`, `step.started`,
`message.logged`, `step.ended`, `test.ended`, `suite.ended`, `status.changed`,
`resultfile.created`, `run.ended`.

```jsonl
{"v":1,"seq":6,"t":1791581563.542,"type":"test.started","id":"s1-t1","parent":"s1","name":"Passing","longname":"Sample.Passing","lineno":6}
{"v":1,"seq":61,"t":1791581563.601,"type":"test.ended","id":"s1-t2","status":"FAIL","message":"1 != 2","elapsed":0.004}
```

The JSON Schema [`events-v1.schema.json`](src/robotframework_events/events-v1.schema.json) is the
reference.

## Python API

```python
import json
import robotframework_events
from robotframework_events import from_dict

with open("events.jsonl", encoding="utf-8") as file:
    events = [from_dict(json.loads(line)) for line in file]  # typed dataclasses

robotframework_events.add_callback(fn)  # in-process consumers, e.g. robotcode's debugger
```

## Development

```
pip install -e .[dev]
ruff check . && ruff format --check . && mypy
pytest                 # format, options, schema and id conformance tests
pytest -m bench        # listener overhead
pytest -m e2e          # through robotcode's debugger (needs ../robotcode)
```

The conformance tests also run on Robot Framework's acceptance test data, found through
`RF_ATEST_DIR` or at `../robotframework/atest/testdata`, and are skipped when it is missing.

## Licence

MIT
