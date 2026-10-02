from fake_decision_client import FakeDecisionClient
from fake_surface import FakeSurface

from src.agent.loop import DiscoveryAgent


def test_agent_completes_full_flow_and_reports_correct_outputs():
    surface = FakeSurface()
    decisions = [
        {"reasoning": "start at search", "action": "navigate", "value": "/search"},
        {
            "reasoning": "enter the member id from the goal",
            "action": "type", "role": "textbox", "name": "Member ID",
            "value": "12345", "is_parameter": True, "parameter_name": "memberId",
        },
        {"reasoning": "submit search", "action": "click", "role": "button", "name": "Search"},
        {"reasoning": "read the balance", "action": "read_text", "row_label": "Savings Balance"},
        {
            "reasoning": "goal achieved", "action": "finish",
            "outputs": {"savingsBalance": "$4,210.55"}, "success": True,
        },
    ]
    client = FakeDecisionClient(decisions)
    agent = DiscoveryAgent(surface=surface, decision_client=client, max_steps=10)

    result = agent.run(goal="Look up member 12345 and read their savings balance.")

    assert result.status == "completed"
    assert result.success is True
    assert result.outputs == {"savingsBalance": "$4,210.55"}
    assert len(result.steps) == 5

    # the parameterization flag should have survived into the recorded trace
    type_step = result.steps[1]
    assert type_step.decision["is_parameter"] is True
    assert type_step.decision["parameter_name"] == "memberId"


def test_agent_stops_at_max_steps_if_it_never_finishes():
    surface = FakeSurface()
    # Keeps "clicking search" forever without ever calling finish.
    decisions = [{"reasoning": "keep trying", "action": "click", "role": "button", "name": "Search"}] * 10
    client = FakeDecisionClient(decisions)
    # stuck_after_repeats set high so max_steps is what actually triggers here
    agent = DiscoveryAgent(surface=surface, decision_client=client, max_steps=3, stuck_after_repeats=100)

    result = agent.run(goal="irrelevant for this test")

    assert result.status == "max_steps_exceeded"
    assert len(result.steps) == 3


def test_agent_detects_being_stuck_on_repeated_identical_observations():
    surface = FakeSurface()
    # Every click here lands on the same "not found" state repeatedly.
    decisions = [{"reasoning": "try again", "action": "click", "role": "button", "name": "Search"}] * 10
    client = FakeDecisionClient(decisions)
    agent = DiscoveryAgent(surface=surface, decision_client=client, max_steps=100, stuck_after_repeats=2)

    result = agent.run(goal="irrelevant for this test")

    assert result.status == "stuck"
    assert len(result.steps) < 10