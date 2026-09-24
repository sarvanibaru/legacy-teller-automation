"""
Policy engine: the single chokepoint every action must pass through before
it touches a real surface. Two independent checks happen here:

1. Is this destination even reachable at all? (origin + path allowlist,
   with an explicit blocklist checked first so a block can never be
   accidentally overridden by a loose allow pattern)
2. If reachable, what risk tier does it carry? (generic action-type risk,
   overridden by target-specific risk when one is declared)

This module has no knowledge of Playwright, the LLM, or anything else --
it only knows about URLs, action types, and the rules in policy.yaml.
Keeping it that isolated makes it easy to unit test and easy to reason
about independently of the rest of the system.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

import yaml


class RiskLevel(str, Enum):
    SAFE = "safe"
    REQUIRES_APPROVAL = "requires_approval"
    BLOCKED = "blocked"


class PolicyViolation(Exception):
    """Raised when an action is refused outright -- origin not allowed,
    path not on the allowlist, or path explicitly blocked."""


@dataclass
class TargetOverride:
    path_pattern: re.Pattern
    risk: RiskLevel


class PolicyEngine:
    def __init__(self, policy_path: str | Path):
        with open(policy_path, "r") as f:
            raw = yaml.safe_load(f)

        self.allowed_origins: list[str] = raw.get("allowed_origins", [])

        self.allowed_path_patterns: list[re.Pattern] = [
            re.compile(p) for p in raw.get("allowed_path_patterns", [])
        ]
        self.blocked_path_patterns: list[re.Pattern] = [
            re.compile(p) for p in raw.get("blocked_path_patterns", [])
        ]

        self.action_risk: dict[str, RiskLevel] = {
            action: RiskLevel(risk)
            for action, risk in raw.get("action_risk", {}).items()
        }

        self.target_overrides: list[TargetOverride] = [
            TargetOverride(
                path_pattern=re.compile(o["path_pattern"]),
                risk=RiskLevel(o["risk"]),
            )
            for o in raw.get("target_overrides", [])
        ]

    def check_reachable(self, url: str) -> None:
        """Raises PolicyViolation if this URL must not be visited at all.
        Does not consider risk tier -- a reachable URL can still be
        requires_approval or even blocked via target_overrides; this only
        answers "is the destination in scope at all"."""
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path

        if origin not in self.allowed_origins:
            raise PolicyViolation(f"Origin not allowed: {origin}")

        for pattern in self.blocked_path_patterns:
            if pattern.match(path):
                raise PolicyViolation(f"Path explicitly blocked: {path}")

        if not any(pattern.match(path) for pattern in self.allowed_path_patterns):
            raise PolicyViolation(f"Path not on allowlist: {path}")

    def classify_risk(self, action_type: str, url: str | None = None) -> RiskLevel:
        """Returns the risk tier for this action, without raising. Target
        overrides take precedence over the generic action-type risk."""
        if url is not None:
            path = urlparse(url).path
            for override in self.target_overrides:
                if override.path_pattern.match(path):
                    return override.risk

        return self.action_risk.get(action_type, RiskLevel.REQUIRES_APPROVAL)

    def enforce(self, action_type: str, url: str | None = None) -> RiskLevel:
        """The single call sites should use: checks reachability (raises if
        not reachable at all), then returns the risk tier for the caller to
        act on (proceed / pause for approval / refuse)."""
        if url is not None:
            self.check_reachable(url)

        risk = self.classify_risk(action_type, url)
        if risk == RiskLevel.BLOCKED:
            raise PolicyViolation(
                f"Action '{action_type}' targeting {url} is blocked by policy"
            )
        return risk