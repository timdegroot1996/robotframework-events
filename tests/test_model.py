"""Typed event classes and the JSON Schema agree with each other and with the listener."""

from dataclasses import MISSING, fields

import pytest
from jsonschema import ValidationError

from conftest import VALIDATOR
from robotframework_events import events, from_dict, schema

ENVELOPE = {"v", "seq", "t", "type"}


def test_schema_is_valid_draft_2020_12():
    VALIDATOR.check_schema(schema())


def test_schema_covers_every_event_class():
    conditional = {rule["if"]["properties"]["type"]["const"] for rule in schema()["allOf"]}
    assert conditional == set(events.EVENT_CLASSES)


@pytest.mark.parametrize("type_", sorted(events.EVENT_CLASSES))
def test_schema_and_class_have_the_same_fields(type_):
    definition = schema()["$defs"][type_]
    cls = events.EVENT_CLASSES[type_]
    own = [f for f in fields(cls) if f.name not in ENVELOPE]
    assert set(definition["properties"]) == {f.name for f in own}
    required = {f.name for f in own if f.default is MISSING and f.default_factory is MISSING}
    assert set(definition["required"]) == required


def test_from_dict_ignores_unknown_fields():
    event = from_dict(
        {
            "v": 1,
            "seq": 3,
            "t": 1.5,
            "type": "step.ended",
            "id": "s1-t1-k1",
            "status": "PASS",
            "elapsed": 0.1,
            "later": "field",
        }
    )
    assert isinstance(event, events.StepEnded)
    assert event.type == "step.ended" and event.status == "PASS"
    assert "later" not in event.to_dict()


def test_unknown_type_is_kept_and_valid():
    data = {"v": 1, "seq": 9, "t": 2.0, "type": "library.imported", "name": "Collections"}
    event = from_dict(data)
    assert isinstance(event, events.UnknownEvent)
    assert event.type == "library.imported" and event.to_dict() == data
    VALIDATOR.validate(data)


@pytest.mark.parametrize(
    "data",
    [
        {"seq": 1, "t": 1.0, "type": "run.ended"},
        {"v": 1, "seq": 1, "t": 1.0, "type": "run.ended", "status": "PASS"},
    ],
    ids=["no envelope field", "no required field"],
)
def test_from_dict_rejects_missing_fields(data):
    with pytest.raises(ValueError):
        from_dict(data)
    with pytest.raises(ValidationError):
        VALIDATOR.validate(data)


def test_schema_rejects_bad_values():
    base = {"v": 1, "seq": 1, "t": 1.0, "type": "step.ended", "elapsed": 0.1}
    with pytest.raises(ValidationError):
        VALIDATOR.validate({**base, "id": "s1-t1-k1", "status": "PASSED"})
    with pytest.raises(ValidationError):
        VALIDATOR.validate({**base, "id": "t1", "status": "PASS"})
