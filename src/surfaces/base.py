"""
The Surface abstraction is the seam between "how we perceive and act on a
concrete UI" and everything above it (the agent loop, the replay engine).
Both of those only ever talk to this interface -- they never know whether
they're driving a browser, a legacy web app, or (eventually) a desktop
app's accessibility tree. That's the whole point: swap the implementation,
keep everything above it unchanged.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

ActionType = Literal["navigate", "click", "type", "read_text"]


@dataclass
class Observation:
    """What the surface currently perceives. accessibility_tree is the
    primary signal an LLM reasons over; screenshot_path is secondary,
    used for evidence and for cases the tree alone doesn't capture."""
    url: str
    accessibility_tree: str
    screenshot_path: str | None = None


@dataclass
class Action:
    type: ActionType
    target: Any | None = None       # a TargetDescriptor; see targeting.py
    value: str | None = None        # text to type, or a URL to navigate to


@dataclass
class ActResult:
    success: bool
    resolved_via: str | None = None   # which locator strategy actually worked
    error: str | None = None
    extracted_text: str | None = None  # populated for read_text actions


class Surface(ABC):
    @abstractmethod
    def observe(self) -> Observation:
        """Return the current perceivable state."""

    @abstractmethod
    def act(self, action: Action) -> ActResult:
        """Perform one action. Must enforce policy internally before
        acting -- callers should never need to check policy separately."""

    @abstractmethod
    def element_visible(self, target: Any) -> bool:
        """Check whether a target currently resolves to a visible element,
        without acting on it. Used by checkpoint and outcome evaluation --
        those need to *ask* whether something is present, not click or
        type into it. Should use a short timeout: this is commonly called
        specifically to distinguish between two already-anticipated
        states (e.g. "did the balance row appear, or the not-found
        message?"), not to wait out a slow load."""

    @abstractmethod
    def current_url(self) -> str:
        """Just the URL, with no accessibility-tree read and no
        screenshot. Used wherever only the destination matters (risk
        classification before deciding whether to escalate) and a full
        observe() would be wasteful."""