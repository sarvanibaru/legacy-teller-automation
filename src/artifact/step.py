"""
A Step is one action in the recorded flow. It deliberately mirrors the
runtime Action/Surface vocabulary (navigate/click/type/read_text) so a
replay engine can translate a Step into an Action almost mechanically --
the two are the same concept, just at different points in time (one is
what's saved, one is what's executed).

Two things a runtime Action doesn't need but a saved Step does:
  - `value` here is a ValueSource (literal or param reference), not a raw
    string, since a saved step's text might come from the caller.
  - `postcondition` lets a step assert it actually worked, rather than
    assuming a click succeeded just because it didn't raise.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from src.artifact.conditions import Condition
from src.artifact.values import ValueSource
from src.surfaces.targeting import TargetDescriptor

StepAction = Literal["navigate", "click", "type", "read_text"]


class Step(BaseModel):
    id: str
    action: StepAction
    target: Optional[TargetDescriptor] = None
    value: Optional[ValueSource] = None
    postcondition: Optional[Condition] = None
    """What confirms this specific step reached the state it expected --
    e.g. after clicking Search, assert the results area or a "not found"
    message is now present. Without this, a failed click and a successful
    one look identical: neither raises, so nothing tells you it actually
    worked."""
