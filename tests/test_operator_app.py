from types import SimpleNamespace

from src.escalation.intervention import EscalationManager
from src.escalation.operator_app import create_operator_app
from src.escalation.session_controller import SessionController


def test_index_shows_no_active_intervention_initially(tmp_path):
    session = SessionController()
    escalation = EscalationManager(session=session, evidence_dir=tmp_path)
    app = create_operator_app(escalation)
    client = app.test_client()

    response = client.get("/")
    assert response.status_code == 200
    assert b"No active intervention" in response.data


def test_index_shows_approval_request_context(tmp_path):
    session = SessionController()
    escalation = EscalationManager(session=session, evidence_dir=tmp_path)
    observation = SimpleNamespace(
        url="http://localhost:5001/member/12345/sub-account/submit",
        accessibility_tree='button "Confirm and Open Account"',
        screenshot_path=None,
    )
    escalation.raise_intervention(
        kind="approval", reason="submit requires approval", observation=observation,
        proposed_action={"action": "click", "name": "Confirm and Open Account"},
    )

    app = create_operator_app(escalation)
    client = app.test_client()
    response = client.get("/")

    assert b"submit requires approval" in response.data
    assert b"Approve" in response.data
    assert b"Reject" in response.data


def test_index_shows_resume_button_for_takeover_kind(tmp_path):
    session = SessionController()
    escalation = EscalationManager(session=session, evidence_dir=tmp_path)
    observation = SimpleNamespace(url="http://x/search", accessibility_tree="...", screenshot_path=None)
    escalation.raise_intervention(kind="takeover", reason="stuck", observation=observation)

    app = create_operator_app(escalation)
    client = app.test_client()
    response = client.get("/")

    assert b"Resume" in response.data
    assert b"Approve" not in response.data


def test_resolve_route_actually_calls_session_resolve(tmp_path):
    session = SessionController()
    escalation = EscalationManager(session=session, evidence_dir=tmp_path)
    observation = SimpleNamespace(url="http://x/y", accessibility_tree="...", screenshot_path=None)
    escalation.raise_intervention(kind="takeover", reason="stuck", observation=observation)
    session.request_human_control(reason="stuck")  # simulate the paused state

    app = create_operator_app(escalation)
    client = app.test_client()

    response = client.post("/resolve", data={"approved": "true", "note": "fixed via console"})

    assert response.status_code == 302  # redirect back to /
    assert session.current_owner == "agent"


def test_screenshot_route_returns_404_when_none_available(tmp_path):
    session = SessionController()
    escalation = EscalationManager(session=session, evidence_dir=tmp_path)
    app = create_operator_app(escalation)
    client = app.test_client()

    response = client.get("/screenshot")
    assert response.status_code == 404