from __future__ import annotations

from src.artifact.capability import AppProfile, Capability
from src.artifact.conditions import ElementVisibleCondition, TextPresentCondition
from src.artifact.io_spec import InputParam, OutputField
from src.artifact.recovery import Outcome
from src.artifact.step import Step
from src.artifact.values import LiteralValue, ParamValue
from src.surfaces.targeting import TargetDescriptor


def build_subaccount_confirm_capability() -> Capability:
    """
    Hand-written capability reaching the sub-account's irreversible
    confirmation step. Assumes it starts already on a specific member's
    detail page -- the same "already positioned, already authenticated"
    assumption the balance-lookup capability makes, just a different
    entry point. One capability's natural ending point (viewing a
    member's detail page) is a reasonable starting point for another.

    Deliberately minimal: accepts the sub-account form's defaults
    (Savings, $25.00) rather than parameterizing them, since this
    capability's purpose is demonstrating the approval gate on the final
    submit step, not being a complete, production-ready capability.
    """
    return Capability(
        capability_id="member.open_sub_account_confirm_demo",
        description="Open a new sub-account for the current member, accepting form defaults, reaching the irreversible confirm step.",
        app_profile=AppProfile(vendor="MockBank", product="CoreTeller", version="1.0-mock"),
        approval_state="draft",
        inputs=[],
        outputs=[],
        steps=[
            Step(
                id="s1",
                action="click",
                target=TargetDescriptor.by_role("button", "Open New Sub-Account"),
            ),
            Step(
                id="s2",
                action="click",
                target=TargetDescriptor.by_role("button", "Continue"),
            ),
            Step(
                id="s3",
                action="click",
                target=TargetDescriptor.by_role("button", "Confirm and Open Account"),
            ),
        ],
        outcomes=[],
        recoveries=[],
        checkpoint=TextPresentCondition(pattern="Sub-Account Created Successfully"),
    )


def build_balance_lookup_capability() -> Capability:
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