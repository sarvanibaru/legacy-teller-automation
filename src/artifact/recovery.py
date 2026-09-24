"""
Outcome and Recovery are what let replay tell apart three fundamentally
different things that can happen mid-run:

  - a declared Outcome: a legitimate result the caller needs to know
    about ("no such member"), not a crash. terminal=True means replay
    stops here and reports this outcome rather than continuing.
  - a Recovery: a known, transient hiccup (an interstitial dialog, a slow
    load) that can be handled automatically and the run continues.
  - anything neither of these catches: a hard failure, reported with
    enough detail to debug (handled by the replay engine itself, not
    declared in the artifact -- there's nothing to declare about the
    unknown).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from src.artifact.conditions import Condition
from src.artifact.step import Step


class Outcome(BaseModel):
    code: str
    """A stable identifier the caller can branch on, e.g. "MEMBER_NOT_FOUND"."""
    detector: Condition
    terminal: bool = True
    """If True, replay stops as soon as this outcome is detected and
    reports it, rather than continuing to the next step."""
    success: bool
    """Whether this outcome represents the capability's normal successful
    result, or a legitimate-but-unsuccessful result. "No such member" is
    success=False but still an Outcome, not a failure -- the caller asked
    a valid question and got a valid answer."""
    description: Optional[str] = None


class Recovery(BaseModel):
    trigger: Condition
    """What indicates this known, recoverable condition is present."""
    action: Optional[Step] = None
    """The step to perform to recover (e.g. click a "Dismiss" button on a
    known interstitial). None means "just wait and retry the action that
    triggered this," for purely transient conditions like a slow load."""
    max_attempts: int = 3
    wait_before_retry_ms: int = 1000
