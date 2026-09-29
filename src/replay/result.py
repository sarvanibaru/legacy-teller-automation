"""
The three-way result contract every replay returns, per the brief's
explicit requirement to distinguish these:
  - success: the capability's normal outcome, with typed outputs.
  - business_outcome: a legitimate, declared, non-default result the
    caller needs to know about (e.g. "no such member") -- not a crash.
  - failed: a genuine hard failure, with enough to debug: which step,
    what was expected, what was actually observed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

ReplayStatus = Literal["success", "business_outcome", "failed"]


@dataclass
class ReplayResult:
    status: ReplayStatus

    # populated on status == "success"
    outputs: Optional[dict] = None

    # populated on status == "business_outcome"
    outcome_code: Optional[str] = None
    outcome_success: Optional[bool] = None

    # populated on status == "failed"
    step_id: Optional[str] = None
    expected: Optional[str] = None
    observed: Optional[str] = None
    error: Optional[str] = None

    # populated whenever available, regardless of status
    evidence_ref: Optional[str] = None