"""
Capability is the complete artifact: everything an AI agent or a human
reviewer needs to understand what this does, what it needs, and what it
returns, without reading a raw model transcript.

`app_profile` identifies which vendor product/version this capability was
recorded against. It's the anchor for the multi-tenant reuse story
(REPORT.md Section 4): two tenants running the same underlying product
share app_profile, and a capability recorded against one is a candidate
for reuse against the other, with per-tenant differences expressed as a
small overlay (out of scope to implement here, but this field is what a
future overlay-resolution step would key off of).

`approval_state` gates unattended replay: a capability starts as "draft"
and can be promoted to "approved" once it's been proven reliable -- the
replay engine (Phase 5) refuses to run a draft capability unattended.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel

from src.artifact.conditions import Condition
from src.artifact.io_spec import InputParam, OutputField
from src.artifact.recovery import Outcome, Recovery
from src.artifact.step import Step


class AppProfile(BaseModel):
    vendor: str
    product: str
    version: Optional[str] = None


class Capability(BaseModel):
    schema_version: str = "1.0"
    capability_id: str
    """A stable, human-readable identifier, e.g. "member.read_savings_balance"."""
    version: int = 1
    description: str
    app_profile: AppProfile
    approval_state: Literal["draft", "approved"] = "draft"

    inputs: List[InputParam] = []
    outputs: List[OutputField] = []
    steps: List[Step]
    outcomes: List[Outcome] = []
    recoveries: List[Recovery] = []
    checkpoint: Condition
    """The overall success condition, checked after all steps complete."""
