"""
The observe -> decide -> act loop. The agent starts already positioned on
the app's entry point (the harness handles authentication before calling
run() -- the agent never sees credentials, matching the same assumption
saved capabilities make). Each turn: observe the current accessibility
tree, ask the LLM what to do next via a forced tool call, execute that
action through the Surface, and feed the result back for the next turn.

Two stopping conditions beyond the model calling finish():
  - max_steps: a hard ceiling so a confused agent can't loop forever.
  - stuck detection: if the observation is identical for several turns in
    a row despite actions being taken, that's a strong signal nothing is
    progressing -- stop rather than burn further API calls uselessly.
    (Escalating this to a human, rather than just stopping, is Phase 7.)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from src.surfaces.base import Action, Surface
from src.surfaces.targeting import TargetDescriptor

SYSTEM_PROMPT_TEMPLATE = """\
You are operating a legacy internal bank teller application through its
accessibility tree, the same way a screen reader would perceive it. You
cannot see raw HTML or pixels -- only element roles, accessible names,
and text content.

Your goal for this run:
{goal}

You act by calling the take_action tool, exactly once per turn. Available
actions:
  - navigate: go to a URL path (value = the path, e.g. "/search")
  - click: click a button or link, identified by role+name (e.g. role="button", name="Search")
  - type: type text into a field, identified by role+name (e.g. role="textbox", name="Member ID"), value = the text
  - read_text: read the value next to a labeled field. Use row_label for
    a field shown as a label/value pair (e.g. row_label="Savings Balance").
  - finish: call this once the goal is fully achieved. Include "outputs"
    (a map of output name to the value you read) and "success": true.
    If you become stuck and cannot proceed, call finish with
    "success": false and explain why in "reasoning".

Important: if a value you type or navigate to was specifically named in
the goal (like a particular ID), set is_parameter=true and give it a
short parameter_name -- this marks it as something a caller should be
able to supply, rather than a fixed value.

Take one action, observe the result, then decide the next one. Do not
guess ahead -- react to what you actually observe.
"""


@dataclass
class DiscoveryStepRecord:
    step_index: int
    reasoning: str
    decision: dict
    action_taken: Optional[dict]
    act_result: Optional[dict]
    observation_after: dict


@dataclass
class DiscoveryResult:
    status: str  # "completed" | "max_steps_exceeded" | "stuck"
    goal: str
    steps: list = field(default_factory=list)
    outputs: Optional[dict] = None
    success: Optional[bool] = None
    starting_url: Optional[str] = None
    """Where the surface was positioned before the agent took its first
    action. The emitter uses this to reconstruct an explicit navigate step
    even when the agent itself didn't need one -- without it, an emitted
    artifact silently assumes replay always starts from wherever this
    particular discovery run happened to begin, which doesn't hold in
    general."""


def _decision_to_target(decision: dict) -> Optional[TargetDescriptor]:
    if decision.get("role") and decision.get("name"):
        return TargetDescriptor.by_role(decision["role"], decision["name"])
    if decision.get("row_label"):
        return TargetDescriptor.by_row_label(decision["row_label"])
    return None


def _decision_to_action(decision: dict) -> Action:
    return Action(
        type=decision["action"],
        target=_decision_to_target(decision),
        value=decision.get("value"),
    )


def _observation_hash(observation) -> str:
    return hashlib.sha256(
        (observation.url + observation.accessibility_tree).encode()
    ).hexdigest()


class DiscoveryAgent:
    def __init__(self, surface: Surface, decision_client, evidence_logger=None,
                 max_steps: int = 15, stuck_after_repeats: int = 3, escalation=None):
        self.surface = surface
        self.decision_client = decision_client
        self.logger = evidence_logger
        self.max_steps = max_steps
        self.stuck_after_repeats = stuck_after_repeats
        self.escalation = escalation
        """Optional EscalationManager. When provided, a stuck condition
        pauses for a human to take over the live session instead of just
        stopping -- and once they resume, the loop continues rather than
        ending, since the human may have unblocked whatever the agent
        couldn't resolve on its own."""

    def run(self, goal: str) -> DiscoveryResult:
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(goal=goal)

        observation = self.surface.observe()
        starting_url = observation.url
        messages = [{
            "role": "user",
            "content": (
                f"Current page: {observation.url}\n\n"
                f"Accessibility tree:\n{observation.accessibility_tree}"
            ),
        }]

        steps: list[DiscoveryStepRecord] = []
        last_hash = _observation_hash(observation)
        repeat_count = 0

        for step_index in range(self.max_steps):
            response = self.decision_client.send(system_prompt, messages)
            tool_use = next(b for b in response.content if b.type == "tool_use")
            decision = tool_use.input

            if self.logger:
                self.logger.log(
                    "agent_decision",
                    step_index=step_index,
                    reasoning=decision.get("reasoning"),
                    action=decision.get("action"),
                )

            messages.append({"role": "assistant", "content": response.content})

            if decision["action"] == "finish":
                steps.append(DiscoveryStepRecord(
                    step_index=step_index,
                    reasoning=decision.get("reasoning", ""),
                    decision=decision,
                    action_taken=None,
                    act_result=None,
                    observation_after={"url": observation.url, "accessibility_tree": observation.accessibility_tree},
                ))
                return DiscoveryResult(
                    status="completed",
                    goal=goal,
                    steps=steps,
                    outputs=decision.get("outputs"),
                    success=decision.get("success", True),
                    starting_url=starting_url,
                )

            action = _decision_to_action(decision)
            result = self.surface.act(action)
            observation = self.surface.observe()

            if self.logger:
                self.logger.log(
                    "agent_step_result",
                    step_index=step_index,
                    action=decision["action"],
                    success=result.success,
                    resolved_via=result.resolved_via,
                    error=result.error,
                )

            steps.append(DiscoveryStepRecord(
                step_index=step_index,
                reasoning=decision.get("reasoning", ""),
                decision=decision,
                action_taken={"type": action.type, "value": action.value},
                act_result={
                    "success": result.success,
                    "resolved_via": result.resolved_via,
                    "error": result.error,
                    "extracted_text": result.extracted_text,
                },
                observation_after={"url": observation.url, "accessibility_tree": observation.accessibility_tree},
            ))

            tool_result_payload = {
                "action_success": result.success,
                "error": result.error,
                "extracted_text": result.extracted_text,
                "new_observation": {
                    "url": observation.url,
                    "accessibility_tree": observation.accessibility_tree,
                },
            }
            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(tool_result_payload),
                }],
            })

            current_hash = _observation_hash(observation)
            if current_hash == last_hash:
                repeat_count += 1
            else:
                repeat_count = 0
            last_hash = current_hash

            if repeat_count >= self.stuck_after_repeats:
                if self.logger:
                    self.logger.log("agent_stuck", step_index=step_index)

                if self.escalation is None:
                    return DiscoveryResult(status="stuck", goal=goal, steps=steps, starting_url=starting_url)

                request = self.escalation.raise_intervention(
                    kind="takeover",
                    reason=f"No progress after {repeat_count + 1} identical observations in a row",
                    observation=observation,
                    goal=goal,
                    step_id=f"step_{step_index}",
                )
                if self.logger:
                    self.logger.log("escalation_raised", kind="takeover", request_id=request.request_id)

                resolution = self.escalation.wait_for_resolution(timeout=None)
                if self.logger:
                    self.logger.log("escalation_resolved", resolution=resolution)

                if resolution is None or not resolution.get("approved"):
                    # Human declined to continue, or the wait timed out --
                    # stop cleanly rather than looping on a known dead end.
                    return DiscoveryResult(status="stuck", goal=goal, steps=steps, starting_url=starting_url)

                # A human may have changed the page during their turn --
                # re-observe and fold that into the SAME last message
                # (appending a new separate user message here would
                # violate the API's alternating user/assistant structure,
                # since the previous message was already role="user").
                fresh_observation = self.surface.observe()
                messages[-1]["content"].append({
                    "type": "text",
                    "text": (
                        "A human operator just took over and may have changed "
                        "the page. Continue toward the goal from this current "
                        f"state.\n\nCurrent page: {fresh_observation.url}\n\n"
                        f"Accessibility tree:\n{fresh_observation.accessibility_tree}"
                    ),
                })
                observation = fresh_observation
                last_hash = _observation_hash(fresh_observation)
                repeat_count = 0

        if self.logger:
            self.logger.log("agent_max_steps_exceeded")
        return DiscoveryResult(status="max_steps_exceeded", goal=goal, steps=steps, starting_url=starting_url)