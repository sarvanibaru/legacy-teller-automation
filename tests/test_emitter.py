from src.agent.loop import DiscoveryResult, DiscoveryStepRecord
from src.artifact.capability import AppProfile, Capability
from src.artifact.emitter import build_capability_from_trace


def make_sample_discovery_result():
    """Mirrors the shape of a real successful discovery run: type member
    ID (parameterized), click Search, read_text the balance, finish --
    with finish's outputs including a bogus echoed-back 'memberId' that
    was never actually read via read_text."""
    steps = [
        DiscoveryStepRecord(
            step_index=0,
            reasoning="enter member id",
            decision={
                "action": "type", "role": "textbox", "name": "Member ID",
                "value": "12345", "is_parameter": True, "parameter_name": "memberId",
                "reasoning": "enter member id",
            },
            action_taken={"type": "type", "value": "12345"},
            act_result={"success": True, "resolved_via": "RoleNameLocator", "error": None, "extracted_text": None},
            observation_after={"url": "http://localhost:5001/search", "accessibility_tree": "..."},
        ),
        DiscoveryStepRecord(
            step_index=1,
            reasoning="click search",
            decision={"action": "click", "role": "button", "name": "Search", "reasoning": "click search"},
            action_taken={"type": "click", "value": None},
            act_result={"success": True, "resolved_via": "RoleNameLocator", "error": None, "extracted_text": None},
            observation_after={"url": "http://localhost:5001/member/12345", "accessibility_tree": "..."},
        ),
        DiscoveryStepRecord(
            step_index=2,
            reasoning="read balance",
            decision={"action": "read_text", "row_label": "Savings Balance", "reasoning": "read balance"},
            action_taken={"type": "read_text", "value": None},
            act_result={"success": True, "resolved_via": "RowLabelLocator", "error": None, "extracted_text": "$4210.55"},
            observation_after={"url": "http://localhost:5001/member/12345", "accessibility_tree": "..."},
        ),
        DiscoveryStepRecord(
            step_index=3,
            reasoning="done",
            decision={
                "action": "finish", "success": True,
                "outputs": {"memberId": "12345", "savingsBalance": "$4210.55"},
                "reasoning": "done",
            },
            action_taken=None,
            act_result=None,
            observation_after={"url": "http://localhost:5001/member/12345", "accessibility_tree": "..."},
        ),
    ]
    return DiscoveryResult(
        status="completed",
        goal="Look up member 12345 and read their current savings balance.",
        steps=steps,
        outputs={"memberId": "12345", "savingsBalance": "$4210.55"},
        success=True,
    )


def test_emitted_capability_has_three_action_steps_not_four():
    result = make_sample_discovery_result()
    capability = build_capability_from_trace(
        result, capability_id="member.read_savings_balance",
        description="auto-generated", app_profile=AppProfile(vendor="MockBank", product="CoreTeller"),
    )
    assert len(capability.steps) == 3  # finish is not a Step


def test_member_id_becomes_a_parameterized_input_with_digit_pattern():
    result = make_sample_discovery_result()
    capability = build_capability_from_trace(
        result, capability_id="x", description="x",
        app_profile=AppProfile(vendor="MockBank", product="CoreTeller"),
    )
    assert len(capability.inputs) == 1
    assert capability.inputs[0].name == "memberId"
    assert capability.inputs[0].pattern == r"^\d+$"

    type_step = capability.steps[0]
    assert type_step.value.kind == "param"
    assert type_step.value.param == "memberId"


def test_bogus_echoed_output_is_dropped_but_real_extraction_is_kept():
    result = make_sample_discovery_result()
    capability = build_capability_from_trace(
        result, capability_id="x", description="x",
        app_profile=AppProfile(vendor="MockBank", product="CoreTeller"),
    )
    output_names = {o.name for o in capability.outputs}
    assert output_names == {"savingsBalance"}  # memberId silently dropped
    assert capability.outputs[0].extract_from_step == "s3"
    assert capability.outputs[0].parse == "currency"
    assert capability.outputs[0].type == "number"


def test_checkpoint_is_inferred_from_last_read_text_step():
    result = make_sample_discovery_result()
    capability = build_capability_from_trace(
        result, capability_id="x", description="x",
        app_profile=AppProfile(vendor="MockBank", product="CoreTeller"),
    )
    assert capability.checkpoint.kind == "element_visible"
    assert capability.checkpoint.target.strategies[0].row_label == "Savings Balance"


def test_emitted_capability_starts_as_draft_with_no_outcomes():
    result = make_sample_discovery_result()
    capability = build_capability_from_trace(
        result, capability_id="x", description="x",
        app_profile=AppProfile(vendor="MockBank", product="CoreTeller"),
    )
    assert capability.approval_state == "draft"
    assert capability.outcomes == []


def test_synthetic_navigate_is_prepended_when_agent_skipped_navigating():
    """The agent's own run started already on /search (via the harness's
    login), so it never called navigate itself. The emitted artifact
    still needs one, so replay doesn't silently assume the browser
    already happens to be on the right page."""
    result = make_sample_discovery_result()
    result.starting_url = "http://localhost:5001/search"

    capability = build_capability_from_trace(
        result, capability_id="x", description="x",
        app_profile=AppProfile(vendor="MockBank", product="CoreTeller"),
    )

    assert len(capability.steps) == 4  # 3 original + 1 synthetic navigate
    assert capability.steps[0].action == "navigate"
    assert capability.steps[0].value.value == "/search"

    # everything else shifts down by one step id
    type_step = capability.steps[1]
    assert type_step.action == "type"
    assert type_step.value.param == "memberId"

    # output extraction still points at the correct (shifted) step id
    assert capability.outputs[0].extract_from_step == "s4"


def test_no_synthetic_navigate_added_when_agent_already_navigated():
    """If the agent's first real action already was a navigate, don't
    add a second, redundant one."""
    result = make_sample_discovery_result()
    result.starting_url = "http://localhost:5001/blank"
    result.steps.insert(0, DiscoveryStepRecord(
        step_index=-1,
        reasoning="go to search",
        decision={"action": "navigate", "value": "/search", "reasoning": "go to search"},
        action_taken={"type": "navigate", "value": "/search"},
        act_result={"success": True, "resolved_via": "navigate", "error": None, "extracted_text": None},
        observation_after={"url": "http://localhost:5001/search", "accessibility_tree": "..."},
    ))

    capability = build_capability_from_trace(
        result, capability_id="x", description="x",
        app_profile=AppProfile(vendor="MockBank", product="CoreTeller"),
    )

    navigate_steps = [s for s in capability.steps if s.action == "navigate"]
    assert len(navigate_steps) == 1  # not duplicated


def test_emitted_capability_round_trips_through_json():
    result = make_sample_discovery_result()
    capability = build_capability_from_trace(
        result, capability_id="x", description="x",
        app_profile=AppProfile(vendor="MockBank", product="CoreTeller"),
    )
    restored = Capability.model_validate_json(capability.model_dump_json())
    assert len(restored.steps) == 3
    assert restored.outputs[0].name == "savingsBalance"