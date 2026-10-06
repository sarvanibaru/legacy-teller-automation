"""
A Surface decorator: wraps any other Surface implementation and adds two
things uniformly -- a lease check before every action, and an approval
pause for anything policy classifies as requires_approval.

Risk is classified using the TARGET'S ACCESSIBLE NAME, not the current
URL, for click actions. This matters: a click's "current page" is the
page the button lives on, not wherever it submits to -- a URL-based
target_override keyed on the destination would never fire for a real
click, since you're never actually "on" that URL until after the click
completes. Classifying by what's being clicked, rather than where you
currently are, is what actually gates the right thing at the right time.
"""
from __future__ import annotations

from src.escalation.intervention import EscalationManager
from src.safety.policy import PolicyEngine, RiskLevel
from src.surfaces.base import Action, ActResult, Observation, Surface


def _target_name(action: Action) -> str | None:
    if action.target is None:
        return None
    strategy = action.target.strategies[0]
    return getattr(strategy, "name", None)


class EscalatingSurface(Surface):
    def __init__(self, inner: Surface, policy: PolicyEngine, escalation: EscalationManager,
                 capability_id=None, goal=None):
        self.inner = inner
        self.policy = policy
        self.escalation = escalation
        self.capability_id = capability_id
        self.goal = goal

    def observe(self) -> Observation:
        return self.inner.observe()

    def element_visible(self, target) -> bool:
        return self.inner.element_visible(target)

    def current_url(self) -> str:
        return self.inner.current_url()

    def act(self, action: Action) -> ActResult:
        try:
            self.escalation.session.assert_agent_turn()

            check_url = action.value if action.type == "navigate" else self.inner.current_url()
            target_name = _target_name(action)
            risk = self.policy.classify_risk(action.type, url=check_url, target_name=target_name)

            if risk == RiskLevel.BLOCKED:
                return ActResult(success=False, error=f"Blocked by policy: '{action.type}' targeting {target_name or check_url}")

            if risk == RiskLevel.REQUIRES_APPROVAL:
                observation = self.inner.observe()
                proposed_action = {
                    "action": action.type,
                    "target": action.target.model_dump() if action.target is not None else None,
                    "value": action.value,
                }
                self.escalation.raise_intervention(
                    kind="approval",
                    reason=f"'{action.type}' action on '{target_name or check_url}' requires human approval",
                    observation=observation,
                    capability_id=self.capability_id,
                    goal=self.goal,
                    proposed_action=proposed_action,
                )
                resolution = self.escalation.wait_for_resolution(timeout=None)
                if resolution is None or not resolution.get("approved"):
                    note = resolution.get("note") if resolution else "no resolution (timed out)"
                    return ActResult(success=False, error=f"Action rejected by human reviewer: {note}")

            return self.inner.act(action)

        except Exception as e:
            return ActResult(success=False, error=f"{type(e).__name__}: {e}")