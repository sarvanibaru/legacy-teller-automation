import json

from pydantic import TypeAdapter

from src.artifact.conditions import (
    AllOfCondition,
    Condition,
    TextPresentCondition,
    UrlMatchesCondition,
)

ConditionAdapter = TypeAdapter(Condition)


def test_text_present_round_trips_through_json():
    original = TextPresentCondition(pattern="No member matching")
    as_json = original.model_dump_json()
    restored = ConditionAdapter.validate_json(as_json)
    assert isinstance(restored, TextPresentCondition)
    assert restored.pattern == "No member matching"


def test_url_matches_round_trips_through_json():
    original = UrlMatchesCondition(pattern=r"^/member/\d+$")
    restored = ConditionAdapter.validate_json(original.model_dump_json())
    assert isinstance(restored, UrlMatchesCondition)
    assert restored.pattern == r"^/member/\d+$"


def test_all_of_condition_with_nested_conditions_round_trips():
    original = AllOfCondition(
        conditions=[
            UrlMatchesCondition(pattern=r"^/member/\d+$"),
            TextPresentCondition(pattern="Savings Balance"),
        ]
    )
    restored = ConditionAdapter.validate_json(original.model_dump_json())
    assert isinstance(restored, AllOfCondition)
    assert len(restored.conditions) == 2
    assert isinstance(restored.conditions[0], UrlMatchesCondition)
    assert isinstance(restored.conditions[1], TextPresentCondition)


def test_discriminator_field_present_in_serialized_json():
    original = TextPresentCondition(pattern="hello")
    parsed = json.loads(original.model_dump_json())
    assert parsed["kind"] == "text_present"
