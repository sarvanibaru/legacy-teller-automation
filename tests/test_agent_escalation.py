import threading
import time

from fake_decision_client import FakeDecisionClient
from fake_surface import FakeSurface

from src.agent.loop import DiscoveryAgent
from src.escalation.intervention import EscalationManager
from src.escalation.session_controller import SessionController


def test_agent_escalates_when_stuck_and_resumes_after_human_fixes_it(tmp_path):
    surface = FakeSurface()
    session = SessionController()
    escalation = EscalationManager(session=session, evidence_dir=tmp_path)

    decisions = [
        # Nothing typed, so every click lands on the same "not found" state --
        # this is what should trigger stuck detection.
        {"reasoning": "try search", "action": "click", "role": "button", "name": "Search"},
        {"reasoning": "try again", "action": "click", "role": "button", "name": "Search"},
        {"reasoning": "try again", "action": "click", "role": "button", "name": "Search"},
        # After the human fixes things, these should succeed:
        {"reasoning": "read the balance now that it's visible", "action": "read_text", "row_label": "Savings Balance"},
        {"reasoning": "done", "action": "finish", "outputs": {"savingsBalance": "$4,210.55"}, "success": True},
    ]
    client = FakeDecisionClient(decisions)
    agent = DiscoveryAgent(
        surface=surface, decision_client=client, max_steps=10,
        stuck_after_repeats=2, escalation=escalation,
    )

    def simulate_human_fixing_it():
        # Wait until the agent has genuinely paused...
        while session.current_owner != "human":
            time.sleep(0.05)
        # ...simulate the human manually navigating to the right state
        # (standing in for real clicks in a real browser)...
        surface.typed_member_id = "12345"
        surface.page_state = "detail"
        # ...then hand control back.
        session.resolve(approved=True, note="fixed it manually, member was found")

    threading.Thread(target=simulate_human_fixing_it).start()

    result = agent.run(goal="Look up member 12345 and read their savings balance.")

    assert result.status == "completed"
    assert result.success is True
    assert result.outputs == {"savingsBalance": "$4,210.55"}


def test_agent_stops_cleanly_if_human_declines_to_continue(tmp_path):
    surface = FakeSurface()
    session = SessionController()
    escalation = EscalationManager(session=session, evidence_dir=tmp_path)

    decisions = [{"reasoning": "try", "action": "click", "role": "button", "name": "Search"}] * 10
    client = FakeDecisionClient(decisions)
    agent = DiscoveryAgent(
        surface=surface, decision_client=client, max_steps=10,
        stuck_after_repeats=2, escalation=escalation,
    )

    def simulate_human_giving_up():
        while session.current_owner != "human":
            time.sleep(0.05)
        session.resolve(approved=False, note="this goal isn't achievable right now")

    threading.Thread(target=simulate_human_giving_up).start()

    result = agent.run(goal="irrelevant for this test")

    assert result.status == "stuck"