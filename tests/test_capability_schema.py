from src.artifact.capability import Capability
from src.artifact.examples import build_balance_lookup_capability


def test_capability_builds_without_validation_errors():
    capability = build_balance_lookup_capability()
    assert capability.capability_id == "member.read_savings_balance"
    assert len(capability.steps) == 4


def test_capability_round_trips_through_json():
    capability = build_balance_lookup_capability()
    as_json = capability.model_dump_json()
    restored = Capability.model_validate_json(as_json)

    assert restored.capability_id == capability.capability_id
    assert len(restored.steps) == len(capability.steps)
    assert restored.checkpoint.kind == "element_visible"


def test_input_param_is_referenced_by_a_step_value():
    capability = build_balance_lookup_capability()
    param_names = {p.name for p in capability.inputs}
    referenced_params = {
        step.value.param
        for step in capability.steps
        if step.value is not None and step.value.kind == "param"
    }
    assert referenced_params.issubset(param_names)


def test_output_field_references_a_real_step_id():
    capability = build_balance_lookup_capability()
    step_ids = {s.id for s in capability.steps}
    for output in capability.outputs:
        assert output.extract_from_step in step_ids


def test_declared_outcome_is_not_the_default_success_checkpoint():
    capability = build_balance_lookup_capability()
    outcome = capability.outcomes[0]
    assert outcome.success is False
    assert outcome.code == "MEMBER_NOT_FOUND"


def test_no_credentials_or_absolute_urls_in_the_artifact():
    """Guards the two deliberate design decisions: no baked-in
    credentials, and no tenant-specific absolute URLs."""
    as_json = build_balance_lookup_capability().model_dump_json()
    assert "password" not in as_json.lower()
    assert "http://" not in as_json
    assert "https://" not in as_json