"""
InterventionRequest is the context package a stuck agent or a
risky-action policy check hands to a human: which capability/goal, which
step, the current screen, and why it stopped. EscalationManager wraps a
SessionController with the actual persistence (so every intervention and
its eventual resolution leaves an audit trail in evidence/) and the
glue code that raises and resolves one.

Two kinds of intervention, since they need different things from the
human:
  - "takeover": the agent is genuinely stuck. The human needs to operate
    the live browser themselves, then signal resume.
  - "approval": a specific pending action is classified requires_approval
    by policy. The human only needs to review and approve or reject --
    the automation still performs the action itself, only after a yes.
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.escalation.session_controller import SessionController
from src.safety.redaction import redact_value


@dataclass
class InterventionRequest:
    request_id: str
    kind: str  # "takeover" | "approval"
    reason: str
    capability_id: Optional[str] = None
    goal: Optional[str] = None
    step_id: Optional[str] = None
    url: str = ""
    accessibility_tree: str = ""
    screenshot_path: Optional[str] = None
    proposed_action: Optional[dict] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EscalationManager:
    def __init__(self, session: SessionController, evidence_dir="evidence/interventions"):
        self.session = session
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.active_request: Optional[InterventionRequest] = None

    def raise_intervention(
        self,
        kind: str,
        reason: str,
        observation,
        capability_id: Optional[str] = None,
        goal: Optional[str] = None,
        step_id: Optional[str] = None,
        proposed_action: Optional[dict] = None,
    ) -> InterventionRequest:
        request_id = f"int_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        request = InterventionRequest(
            request_id=request_id,
            kind=kind,
            reason=reason,
            capability_id=capability_id,
            goal=goal,
            step_id=step_id,
            url=observation.url,
            accessibility_tree=observation.accessibility_tree,
            screenshot_path=observation.screenshot_path,
            proposed_action=proposed_action,
        )
        self.active_request = request
        self._persist_request(request)
        self.session.request_human_control(reason=reason)
        return request

    def wait_for_resolution(self, timeout: Optional[float] = None) -> Optional[dict]:
        resolution = self.session.wait_until_agent_turn(timeout=timeout)
        if resolution is not None and self.active_request is not None:
            self._persist_resolution(self.active_request.request_id, resolution)
            self.active_request = None
        return resolution

    def _persist_request(self, request: InterventionRequest):
        data = redact_value(dataclasses.asdict(request))
        path = self.evidence_dir / f"{request.request_id}.json"
        path.write_text(json.dumps(data, indent=2))

    def _persist_resolution(self, request_id: str, resolution: dict):
        data = {
            "request_id": request_id,
            **resolution,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }
        path = self.evidence_dir / f"{request_id}_resolution.json"
        path.write_text(json.dumps(data, indent=2))