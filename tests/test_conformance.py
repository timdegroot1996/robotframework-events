"""Id conformance: every emitted id, kind, parent and status matches output.xml.

Converter conformance: events converted from that output.xml have the same ids, and give
the same RunState as the live events (apart from times, sources and line numbers).

Runs on tests/data and on Robot Framework's own acceptance test data
(``RF_ATEST_DIR``, default ``../robotframework/atest/testdata``; skipped when missing).
"""

import os
from pathlib import Path

import pytest
from robot.api import ExecutionResult, ResultVisitor

from conftest import DATA, check_format, run_with_listener
from robotframework_events import RunState, convert, from_dict
from robotframework_events.state import step_label

ROOTS = {"IF/ELSE ROOT", "TRY/EXCEPT ROOT"}
ATEST = Path(os.environ.get("RF_ATEST_DIR", Path(__file__).parents[2] / "robotframework" / "atest" / "testdata"))
ATEST_SUITES = [
    "running/for",
    "running/if",
    "running/try_except",
    "running/while",
    "running/group",
    "running/skip",
    "running/flatten.robot",
    "running/steps_after_failure.robot",
    "running/failures_in_teardown.robot",
    "running/test_template.robot",
    "running/return.robot",
    "running/pass_execution.robot",
    "running/continue_on_failure.robot",
    "running/invalid_break_and_continue.robot",
    "keywords/embedded_arguments.robot",
    "keywords/optional_given_when_then.robot",
    "standard_libraries/builtin/run_keyword.robot",
    "standard_libraries/builtin/run_keyword_and_return_status.robot",
    "standard_libraries/builtin/wait_until_keyword_succeeds.robot",
]


def emitted_parent(item):
    """The id of the nearest ancestor that is emitted (IF/TRY roots are skipped)."""
    parent = item.parent
    while getattr(parent, "type", None) in ROOTS:
        parent = parent.parent
    return parent.id


class Expected(ResultVisitor):
    def __init__(self):
        self.items = []

    def start_suite(self, suite):
        self.items.append(("suite", suite.id, suite.parent.id if suite.parent else None, suite.status))

    def start_test(self, test):
        self.items.append(("test", test.id, test.parent.id, test.status))

    def start_body_item(self, item):
        if item.type not in ROOTS and item.type != "MESSAGE":
            self.items.append((item.type, item.id, emitted_parent(item), item.status))

    def visit_message(self, message):
        pass


def actual_items(events):
    ended = {}
    for e in events:
        if e["type"].endswith(".ended") and "id" in e:
            ended[(e["type"].split(".")[0], e["id"])] = e["status"]
        elif e["type"] == "status.changed":
            ended[(e["item"], e["id"])] = e["status"]
    # output.xml has no children for flattened keywords
    flattened = {e["id"] for e in events if e.get("flatten")}
    items = []
    for e in events:
        if e["type"] == "step.started" and any(e["id"].startswith(f + "-") for f in flattened):
            continue
        if e["type"] == "suite.started":
            items.append(("suite", e["id"], e.get("parent"), ended[("suite", e["id"])]))
        elif e["type"] == "test.started":
            items.append(("test", e["id"], e.get("parent"), ended[("test", e["id"])]))
        elif e["type"] == "step.started":
            items.append((e["kind"], e["id"], e.get("parent"), ended[("step", e["id"])]))
    return items


# XML cannot hold most control characters, U+FFFE and U+FFFF; output.xml leaves them out
NO_CONTROL = {c: None for c in [*range(32), 0xFFFE, 0xFFFF] if chr(c) not in "\t\n\r"}


def tree(events):
    """What a viewer shows of each suite, test and step, in order; children of flattened keywords left out."""
    state = RunState.from_events(from_dict(e) for e in events)
    flattened = {n.id for n in state.nodes.values() if getattr(n.started, "flatten", None)}
    return [
        (
            node.id,
            node.kind,
            node.parent,
            step_label(node).translate(NO_CONTROL),
            getattr(node.started, "args", None),
            node.status,
            node.message,
            [] if node.id in flattened else [(m.level, m.text.translate(NO_CONTROL)) for m in node.messages],
        )
        for node in state.nodes.values()
        if not any(node.id.startswith(f + "-") for f in flattened)
    ]


def assert_conforms(tmp_path, sources, **options):
    events, output = run_with_listener(tmp_path, sources, **options)
    expected = Expected()
    ExecutionResult(str(output)).visit(expected)
    actual = actual_items(events)
    assert len(actual) == len(expected.items)
    for got, want in zip(actual, expected.items, strict=True):
        assert got == want

    converted = list(convert(output))
    check_format(converted)
    assert actual_items(converted) == expected.items
    for live, replayed in zip(tree(events), tree(converted), strict=True):
        assert live == replayed
    return len(actual)


def test_sample_conforms(tmp_path):
    assert assert_conforms(tmp_path, [DATA / "sample.robot"]) == 43


@pytest.mark.skipif(not ATEST.is_dir(), reason=f"Robot Framework acceptance test data not found at {ATEST}")
@pytest.mark.parametrize("suite", ATEST_SUITES)
def test_atest_suite_conforms(tmp_path, suite):
    path = ATEST / suite
    if not path.exists():
        pytest.skip(f"{suite} not in this Robot Framework checkout")
    resources = ATEST.parent / "testresources"
    assert_conforms(
        tmp_path,
        [path],
        pythonpath=[str(resources / "testlibs"), str(resources / "listeners"), str(resources / "res_and_var_files")],
        variable=[f"TESTRESOURCES:{resources}"],
    )
