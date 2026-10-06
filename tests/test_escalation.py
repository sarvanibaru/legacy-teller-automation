import json
import threading
import time
from types import SimpleNamespace

from src.escalation.intervention import EscalationManager
from src.escalation.session_controller import SessionController


def test_assert_agent_turn_raises_once_human_has_control():
    session = SessionController()
    session.assert_agent_turn()  # should not raise initially

    session.request_human_control(reason="test")
    try:
        session.assert_agent_turn()
        assert False, "expected RuntimeError while human holds the session"
    except RuntimeError:
        pass


def test_resolve_hands_control_back_and_unblocks_waiting_thread():
    session = SessionController()
    session.request_human_control(reason="agent is stuck")

    results = []

    def blocked_automation_thread():
        resolution = session.wait_until_agent_turn(timeout=5)
        results.append(resolution)

    t = threading.Thread(target=blocked_automation_thread)
    t.start()

    time.sleep(0.2)  # give the thread time to actually start blocking
    assert session.current_owner == "human"

    session.resolve(approved=True, note="fixed it manually")
    t.join(timeout=5)

    assert session.current_owner == "agent"
    assert results[0] == {"approved": True, "note": "fixed it manually"}


def test_wait_times_out_if_never_resolved():
    session = SessionController()
    session.request_human_control(reason="stuck")
    result = session.wait_until_agent_turn(timeout=0.2)
    assert result is None


def test_escalation_manager_persists_request_and_resolution(tmp_path):
    session = SessionController()
    manager = EscalationManager(session=session, evidence_dir=tmp_path)

    observation = SimpleNamespace(
        url="http://localhost:5001/member/12345/sub-account/confirm",
        accessibility_tree='button "Confirm and Open Account"',
        screenshot_path=str(tmp_path / "shot.png"),
    )

    request = manager.raise_intervention(
        kind="approval",
        reason="submit_sub_account requires approval",
        observation=observation,
        capability_id="member.open_sub_account",
        step_id="s4",
        proposed_action={"action": "click", "role": "button", "name": "Confirm and Open Account"},
    )

    request_path = tmp_path / f"{request.request_id}.json"
    assert request_path.exists()
    saved = json.loads(request_path.read_text())
    assert saved["kind"] == "approval"
    assert saved["step_id"] == "s4"

    def resolver():
        time.sleep(0.1)
        session.resolve(approved=True, note="looks right, approved")

    threading.Thread(target=resolver).start()
    resolution = manager.wait_for_resolution(timeout=5)

    assert resolution == {"approved": True, "note": "looks right, approved"}

    resolution_path = tmp_path / f"{request.request_id}_resolution.json"
    assert resolution_path.exists()
    saved_resolution = json.loads(resolution_path.read_text())
    assert saved_resolution["approved"] is True


def test_sensitive_data_in_proposed_action_is_redacted(tmp_path):
    session = SessionController()
    manager = EscalationManager(session=session, evidence_dir=tmp_path)

    observation = SimpleNamespace(
        url="http://localhost:5001/login",
        accessibility_tree='textbox "Password"',
        screenshot_path=None,
    )

    request = manager.raise_intervention(
        kind="takeover",
        reason="stuck on login",
        observation=observation,
        proposed_action={"action": "type", "password": "hunter2"},
    )

    saved = json.loads((tmp_path / f"{request.request_id}.json").read_text())
    assert "hunter2" not in json.dumps(saved)