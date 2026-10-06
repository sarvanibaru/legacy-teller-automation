"""
The deterministic replay engine: given a saved Capability and a set of
input parameters, executes it against a live Surface with no LLM in the
decision loop. Every decision was already made at recording time; this
only resolves targets, performs actions, and checks conditions.

Outcomes are checked after *every* step, not just on failure -- a click
that lands on "no such member" doesn't raise or fail as an action, the
page just renders different content. If outcomes were only checked after
a failed action, that case would be missed entirely and the engine would
plow ahead into a step that assumes a member was found.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from src.artifact.capability import Capability
from src.artifact.step import Step
from src.evidence.logger import EvidenceLogger
from src.replay.evaluate import evaluate_condition
from src.replay.result import ReplayResult
from src.surfaces.base import Action, Surface


class InputValidationError(Exception):
    pass


class ReplayEngine:
    def __init__(self, surface: Surface, base_url: str, evidence_logger: EvidenceLogger, escalation=None):
        self.surface = surface
        self.base_url = base_url
        self.logger = evidence_logger
        self.escalation = escalation
        """Optional EscalationManager. When provided, a step that fails
        pauses for a human to take over the live session and fix
        whatever blocked it, then retries that same step once before
        giving up -- matching "a replay hits a condition it can't
        recover from" from the brief, rather than failing immediately."""

    def replay(self, capability: Capability, inputs: dict, allow_draft: bool = False) -> ReplayResult:
        if capability.approval_state != "approved" and not allow_draft:
            self.logger.log(
                "replay_refused",
                capability_id=capability.capability_id,
                reason="not approved for unattended replay",
            )
            return ReplayResult(
                status="failed",
                error=(
                    f"Capability '{capability.capability_id}' is in "
                    f"'{capability.approval_state}' state, not 'approved'. "
                    "Pass allow_draft=True to run it anyway."
                ),
            )

        try:
            self._validate_inputs(capability, inputs)
        except InputValidationError as e:
            return ReplayResult(status="failed", error=str(e))

        self.logger.log(
            "replay_started",
            capability_id=capability.capability_id,
            capability_version=capability.version,
        )

        extracted_by_step: dict[str, str] = {}

        try:
            for step in capability.steps:
                action = self._step_to_action(step, inputs)
                self.logger.log("step_started", step_id=step.id, action=step.action)

                result = self._act_with_escalation(action, step, capability)

                self.logger.log(
                    "step_completed",
                    step_id=step.id,
                    success=result.success,
                    resolved_via=result.resolved_via,
                    error=result.error,
                )

                if result.success and step.action == "read_text":
                    extracted_by_step[step.id] = result.extracted_text

                if not result.success:
                    observation = self.surface.observe()
                    outcome = self._check_outcomes(capability, observation)
                    if outcome is not None:
                        return self._outcome_result(outcome, step.id, observation)

                    return ReplayResult(
                        status="failed",
                        step_id=step.id,
                        expected=f"'{step.action}' action to succeed",
                        observed=result.error,
                        evidence_ref=observation.screenshot_path,
                    )

                observation = self.surface.observe()

                if step.postcondition is not None:
                    if not evaluate_condition(step.postcondition, observation, self.surface):
                        outcome = self._check_outcomes(capability, observation)
                        if outcome is not None:
                            return self._outcome_result(outcome, step.id, observation)

                        return ReplayResult(
                            status="failed",
                            step_id=step.id,
                            expected="step postcondition to be met",
                            observed="postcondition was not met",
                            evidence_ref=observation.screenshot_path,
                        )

                outcome = self._check_outcomes(capability, observation)
                if outcome is not None:
                    return self._outcome_result(outcome, step.id, observation)

            final_observation = self.surface.observe()
            if not evaluate_condition(capability.checkpoint, final_observation, self.surface):
                return ReplayResult(
                    status="failed",
                    expected="capability checkpoint to be met",
                    observed="checkpoint was not met after all steps completed",
                    evidence_ref=final_observation.screenshot_path,
                )

            outputs = self._build_outputs(capability, extracted_by_step)
            self.logger.log("replay_succeeded", capability_id=capability.capability_id, outputs=outputs)
            return ReplayResult(status="success", outputs=outputs)

        except Exception as e:
            self.logger.log("replay_crashed", error=f"{type(e).__name__}: {e}")
            return ReplayResult(
                status="failed",
                error=f"Unexpected error during replay: {type(e).__name__}: {e}",
            )

    def _act_with_escalation(self, action: Action, step: Step, capability: Capability):
        result = self.surface.act(action)
        if result.success or self.escalation is None:
            return result

        observation = self.surface.observe()
        request = self.escalation.raise_intervention(
            kind="takeover",
            reason=f"Step '{step.id}' ('{step.action}') failed: {result.error}",
            observation=observation,
            capability_id=capability.capability_id,
            step_id=step.id,
        )
        self.logger.log("escalation_raised", kind="takeover", request_id=request.request_id, step_id=step.id)

        resolution = self.escalation.wait_for_resolution(timeout=None)
        self.logger.log("escalation_resolved", resolution=resolution, step_id=step.id)

        if resolution is None or not resolution.get("approved"):
            return result  # the original failure stands

        # A human may have fixed the live state -- give the same action
        # one more try before accepting it as a hard failure.
        retried = self.surface.act(action)
        self.logger.log("step_retried_after_escalation", step_id=step.id, success=retried.success)
        return retried

    def _outcome_result(self, outcome, step_id: str, observation) -> ReplayResult:
        self.logger.log("outcome_detected", code=outcome.code, step_id=step_id)
        return ReplayResult(
            status="business_outcome",
            outcome_code=outcome.code,
            outcome_success=outcome.success,
            evidence_ref=observation.screenshot_path,
        )

    def _check_outcomes(self, capability: Capability, observation):
        for outcome in capability.outcomes:
            if evaluate_condition(outcome.detector, observation, self.surface):
                return outcome
        return None

    def _step_to_action(self, step: Step, inputs: dict) -> Action:
        value = None
        if step.value is not None:
            if step.value.kind == "literal":
                value = step.value.value
            elif step.value.kind == "param":
                if step.value.param not in inputs:
                    raise InputValidationError(
                        f"Step '{step.id}' references undeclared input '{step.value.param}'"
                    )
                value = str(inputs[step.value.param])

        if step.action == "navigate" and value is not None:
            value = urljoin(self.base_url, value)

        return Action(type=step.action, target=step.target, value=value)

    def _validate_inputs(self, capability: Capability, inputs: dict):
        for param in capability.inputs:
            if param.name not in inputs:
                raise InputValidationError(f"Missing required input: '{param.name}'")
            value = inputs[param.name]
            if param.pattern is not None and not re.match(param.pattern, str(value)):
                raise InputValidationError(
                    f"Input '{param.name}' value '{value}' does not match required pattern '{param.pattern}'"
                )

    def _build_outputs(self, capability: Capability, extracted_by_step: dict) -> dict:
        outputs = {}
        for field in capability.outputs:
            raw = extracted_by_step.get(field.extract_from_step)
            outputs[field.name] = self._parse_value(raw, field.parse, field.type)
        return outputs

    def _parse_value(self, raw, parse: str, field_type: str):
        if raw is None:
            return None
        if parse == "currency":
            cleaned = raw.replace("$", "").replace(",", "").strip()
            return float(cleaned)
        elif parse == "integer":
            return int(raw.strip())
        else:
            if field_type == "number":
                try:
                    return float(raw)
                except ValueError:
                    return raw
            return raw