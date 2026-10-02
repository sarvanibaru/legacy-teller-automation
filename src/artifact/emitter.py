"""
Converts a DiscoveryResult (the agent's recorded run) into a Capability
artifact -- the step that actually closes the loop the whole project is
built around: the model discovers, the artifact becomes a reusable
capability.

Deliberately conservative in a few places, and worth being honest about:
  - outcomes are NOT auto-populated. A single successful discovery run
    only ever observed the happy path; declaring an outcome it never saw
    would be fabricating confidence. Outcomes get added by a human
    reviewer (or a second, deliberately adversarial discovery run) before
    the capability is promoted out of "draft".
  - an output is only recognized if its value can be traced back to an
    actual read_text extraction in the trace. The model's own "outputs"
    at finish() sometimes just echo an input back (not something it
    actually read off a page) -- those are silently dropped rather than
    turned into a bogus OutputField.
  - the checkpoint is inferred from the last read_text step's target,
    since the agent doesn't declare an explicit success condition itself.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from src.artifact.capability import AppProfile, Capability
from src.artifact.conditions import ElementVisibleCondition, UrlMatchesCondition
from src.artifact.io_spec import InputParam, OutputField
from src.artifact.step import Step
from src.artifact.values import LiteralValue, ParamValue
from src.surfaces.targeting import TargetDescriptor


def _target_from_decision(decision: dict):
    if decision.get("role") and decision.get("name"):
        return TargetDescriptor.by_role(decision["role"], decision["name"])
    if decision.get("row_label"):
        return TargetDescriptor.by_row_label(decision["row_label"])
    return None


def _value_source(decision: dict, base_url: str):
    if decision.get("is_parameter") and decision.get("parameter_name"):
        return ParamValue(param=decision["parameter_name"]), decision.get("value")

    raw_value = decision.get("value")
    if raw_value is None:
        return None, None

    if decision["action"] == "navigate":
        path = urlparse(raw_value).path or raw_value
        return LiteralValue(value=path), raw_value

    return LiteralValue(value=raw_value), raw_value


def build_capability_from_trace(
    discovery_result,
    capability_id: str,
    description: str,
    app_profile: AppProfile,
) -> Capability:
    inputs_by_name: dict[str, InputParam] = {}
    steps: list[Step] = []
    read_text_extractions: dict[str, str] = {}  # extracted value -> step_id
    last_read_text_step = None

    action_records = [s for s in discovery_result.steps if s.decision["action"] != "finish"]
    counter = 1

    starting_url = getattr(discovery_result, "starting_url", None)
    already_starts_with_navigate = bool(action_records) and action_records[0].decision["action"] == "navigate"
    if starting_url and not already_starts_with_navigate:
        # The agent didn't need to navigate during this particular run
        # (it was already there), but replay can't assume that -- make
        # the artifact self-contained by recording the entry point
        # explicitly, exactly as a human author would.
        entry_path = urlparse(starting_url).path or "/"
        steps.append(Step(id=f"s{counter}", action="navigate", value=LiteralValue(value=entry_path)))
        counter += 1

    for record in action_records:
        step_id = f"s{counter}"
        counter += 1
        decision = record.decision
        target = _target_from_decision(decision)
        value_source, raw_value = _value_source(decision, base_url="")

        if decision.get("is_parameter") and decision.get("parameter_name"):
            name = decision["parameter_name"]
            if name not in inputs_by_name:
                pattern = r"^\d+$" if raw_value and raw_value.isdigit() else None
                inputs_by_name[name] = InputParam(
                    name=name,
                    type="string",
                    description=f"Parameter '{name}', identified from the goal during discovery.",
                    pattern=pattern,
                )

        steps.append(Step(
            id=step_id,
            action=decision["action"],
            target=target,
            value=value_source,
        ))

        if decision["action"] == "read_text" and record.act_result and record.act_result.get("success"):
            extracted = record.act_result.get("extracted_text")
            if extracted is not None:
                read_text_extractions[extracted] = step_id
                last_read_text_step = record

    outputs: list[OutputField] = []
    for name, value in (discovery_result.outputs or {}).items():
        matching_step_id = read_text_extractions.get(value)
        if matching_step_id is None:
            # Doesn't trace back to a real extraction (e.g. the model
            # echoed an input parameter back as an "output") -- skip it
            # rather than fabricate a bogus OutputField.
            continue
        parse = "currency" if isinstance(value, str) and value.strip().startswith("$") else "raw"
        field_type = "number" if parse == "currency" else "string"
        outputs.append(OutputField(
            name=name,
            type=field_type,
            description=f"Value extracted during discovery for '{name}'.",
            extract_from_step=matching_step_id,
            parse=parse,
        ))

    if last_read_text_step is not None:
        checkpoint = ElementVisibleCondition(
            target=_target_from_decision(last_read_text_step.decision)
        )
    else:
        final_url = discovery_result.steps[-1].observation_after["url"]
        path = re.escape(urlparse(final_url).path)
        checkpoint = UrlMatchesCondition(pattern=f"^{path}$")

    return Capability(
        capability_id=capability_id,
        description=description,
        app_profile=app_profile,
        approval_state="draft",
        inputs=list(inputs_by_name.values()),
        outputs=outputs,
        steps=steps,
        outcomes=[],
        recoveries=[],
        checkpoint=checkpoint,
    )