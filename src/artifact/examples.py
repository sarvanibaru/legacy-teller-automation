"""
Hand-written example capabilities, used both by the demo/build script and
by tests. Living in src/ rather than scripts/ means they're reliably
importable regardless of how pytest is invoked (plain `pytest` does not
add the current directory to sys.path the way `python3 -m pytest` does --
putting real logic only in scripts/ made that a fragile dependency).
"""
from __future__ import annotations

from src.artifact.capability import AppProfile, Capability
from src.artifact.conditions import ElementVisibleCondition, TextPresentCondition
from src.artifact.io_spec import InputParam, OutputField
from src.artifact.recovery import Outcome
from src.artifact.step import Step
from src.artifact.values import LiteralValue, ParamValue
from src.surfaces.targeting import TargetDescriptor


def build_balance_lookup_capability() -> Capability:
    """
    Hand-written (not agent-generated) artifact for the balance-lookup
    flow. Built directly via the Pydantic models specifically to prove
    the schema can express a real flow before anything depends on it.

    Two deliberate design choices worth noting:
      - No login steps. Baking credentials into a saved artifact would
        violate the "never persist secrets into artifacts" rule even with
        fake credentials -- authentication is assumed to be handled once
        by the platform (an already-authenticated session), not
        per-capability.
      - Relative paths ("/search", not the full origin). The origin is
        tenant-specific and supplied at replay time from tenant config,
        not baked into the artifact -- this keeps one capability reusable
        across tenants that run the same product on different domains.
    """
    return Capability(
        capability_id="member.read_savings_balance",
        description="Look up a member by ID and read their current savings balance.",
        app_profile=AppProfile(vendor="MockBank", product="CoreTeller", version="1.0-mock"),
        approval_state="draft",
        inputs=[
            InputParam(
                name="memberId",
                type="string",
                description="The member ID to search for.",
                pattern=r"^\d+$",
                sensitive=False,
            ),
        ],
        outputs=[
            OutputField(
                name="savingsBalance",
                type="number",
                description="The member's current savings balance.",
                extract_from_step="s4",
                parse="currency",
            ),
        ],
        steps=[
            Step(
                id="s1",
                action="navigate",
                value=LiteralValue(value="/search"),
                postcondition=ElementVisibleCondition(
                    target=TargetDescriptor.by_role("textbox", "Member ID")
                ),
            ),
            Step(
                id="s2",
                action="type",
                target=TargetDescriptor.by_role("textbox", "Member ID"),
                value=ParamValue(param="memberId"),
            ),
            Step(
                id="s3",
                action="click",
                target=TargetDescriptor.by_role("button", "Search"),
            ),
            Step(
                id="s4",
                action="read_text",
                target=TargetDescriptor.by_row_label("Savings Balance"),
            ),
        ],
        outcomes=[
            Outcome(
                code="MEMBER_NOT_FOUND",
                detector=TextPresentCondition(pattern="No member matching"),
                terminal=True,
                success=False,
                description="No member exists with the given ID.",
            ),
        ],
        recoveries=[],
        checkpoint=ElementVisibleCondition(
            target=TargetDescriptor.by_row_label("Savings Balance")
        ),
    )
