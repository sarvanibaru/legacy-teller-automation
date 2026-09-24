import pytest

from src.safety.policy import PolicyEngine, PolicyViolation, RiskLevel


@pytest.fixture
def policy():
    return PolicyEngine("policy.yaml")


def test_allowed_path_is_reachable(policy):
    policy.check_reachable("http://localhost:5001/member/12345")  # should not raise


def test_disallowed_origin_raises(policy):
    with pytest.raises(PolicyViolation):
        policy.check_reachable("http://evil.example.com/member/12345")


def test_unlisted_path_raises(policy):
    with pytest.raises(PolicyViolation):
        policy.check_reachable("http://localhost:5001/admin/delete-everything")


def test_explicitly_blocked_path_raises_even_though_shape_is_plausible(policy):
    with pytest.raises(PolicyViolation):
        policy.check_reachable("http://localhost:5001/member/12345/close")


def test_generic_click_is_safe(policy):
    assert policy.classify_risk("click") == RiskLevel.SAFE


def test_submit_sub_account_requires_approval(policy):
    assert policy.classify_risk("submit_sub_account") == RiskLevel.REQUIRES_APPROVAL


def test_close_account_target_override_is_blocked_even_as_generic_click(policy):
    risk = policy.classify_risk(
        "click", url="http://localhost:5001/member/12345/close"
    )
    assert risk == RiskLevel.BLOCKED


def test_unknown_action_type_defaults_to_requires_approval(policy):
    assert policy.classify_risk("some_new_action_nobody_classified_yet") == (
        RiskLevel.REQUIRES_APPROVAL
    )


def test_enforce_raises_on_blocked_target(policy):
    with pytest.raises(PolicyViolation):
        policy.enforce("click", url="http://localhost:5001/member/12345/close")


def test_enforce_returns_risk_for_reachable_safe_action(policy):
    risk = policy.enforce("navigate", url="http://localhost:5001/member/12345")
    assert risk == RiskLevel.SAFE
