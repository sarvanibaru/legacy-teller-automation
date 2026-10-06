import threading
import time

from src.escalation.intervention import EscalationManager
from src.escalation.session_controller import SessionController
from src.safety.policy import PolicyEngine
from src.surfaces.base import Action
from src.surfaces.escalating_surface import EscalatingSurface
from src.surfaces.targeting import TargetDescriptor

from fake_surface import FakeSurface


def make_wrapped(tmp_path):
    inner = FakeSurface()
    policy = PolicyEngine("policy.yaml")
    session = SessionController()
    escalation = EscalationManager(session=session, evidence_dir=tmp_path)
    wrapped = EscalatingSurface(inner=inner, policy=policy, escalation=escalation)
    return inner, wrapped, session


def test_safe_action_proceeds_immediately_without_escalation(tmp_path):
    inner, wrapped, session = make_wrapped(tmp_path)
    inner.url = "http://localhost:5001/search"
    result = wrapped.act(Action(type="navigate", value="http://localhost:5001/search"))
    assert result.success
    assert session.current_owner == "agent"


def test_requires_approval_fires_by_target_name_even_though_current_page_is_not_the_destination(tmp_path):
    """The real-world case: clicking 'Confirm and Open Account' while
    CURRENTLY on the /confirm page (not /submit, the destination). A
    URL-based check alone would miss this entirely."""
    inner, wrapped, session = make_wrapped(tmp_path)
    inner.url = "http://localhost:5001/member/12345/sub-account/confirm"  # NOT /submit
    inner.page_state = "blank"

    results = []

    def run_action():
        action = Action(type="click", target=TargetDescriptor.by_role("button", "Confirm and Open Account"))
        results.append(wrapped.act(action))

    t = threading.Thread(target=run_action)
    t.start()
    time.sleep(0.2)
    assert session.current_owner == "human"  # genuinely paused, despite URL not matching

    session.resolve(approved=True, note="approved")
    t.join(timeout=5)

    assert results[0].success is True


def test_requires_approval_action_rejected_never_performs_inner_action(tmp_path):
    inner, wrapped, session = make_wrapped(tmp_path)
    inner.url = "http://localhost:5001/member/12345/sub-account/confirm"
    inner.page_state = "blank"

    results = []

    def run_action():
        action = Action(type="click", target=TargetDescriptor.by_role("button", "Confirm and Open Account"))
        results.append(wrapped.act(action))

    t = threading.Thread(target=run_action)
    t.start()
    time.sleep(0.2)
    session.resolve(approved=False, note="not ready")
    t.join(timeout=5)

    assert results[0].success is False
    assert "rejected" in results[0].error.lower()
    assert inner.page_state == "blank"  # inner.act() never ran


def test_blocked_action_fires_by_target_name_even_from_the_prior_page(tmp_path):
    """Same real-world case for the close-account block: current page is
    the member detail page, not /close."""
    inner, wrapped, session = make_wrapped(tmp_path)
    inner.url = "http://localhost:5001/member/12345"  # NOT /close

    result = wrapped.act(Action(type="click", target=TargetDescriptor.by_role("link", "Close Account")))

    assert result.success is False
    assert "blocked" in result.error.lower()
    assert session.current_owner == "agent"


def test_action_fails_cleanly_rather_than_raising_if_lease_already_held_by_human(tmp_path):
    inner, wrapped, session = make_wrapped(tmp_path)
    session.request_human_control(reason="prior escalation in progress")
    result = wrapped.act(Action(type="navigate", value="http://localhost:5001/search"))
    assert result.success is False
    assert "human" in result.error.lower()