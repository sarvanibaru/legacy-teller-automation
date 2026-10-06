from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import yaml


class RiskLevel(str, Enum):
    SAFE = "safe"
    REQUIRES_APPROVAL = "requires_approval"
    BLOCKED = "blocked"


class PolicyViolation(Exception):
    pass


@dataclass
class TargetOverride:
    path_pattern: Optional[re.Pattern]
    action_name: Optional[str]
    risk: RiskLevel


class PolicyEngine:
    def __init__(self, policy_path):
        with open(policy_path, "r") as f:
            raw = yaml.safe_load(f)

        self.allowed_origins: list = raw.get("allowed_origins", [])

        self.allowed_path_patterns = [re.compile(p) for p in raw.get("allowed_path_patterns", [])]
        self.blocked_path_patterns = [re.compile(p) for p in raw.get("blocked_path_patterns", [])]

        self.action_risk = {
            action: RiskLevel(risk) for action, risk in raw.get("action_risk", {}).items()
        }

        self.target_overrides = [
            TargetOverride(
                path_pattern=re.compile(o["path_pattern"]) if o.get("path_pattern") else None,
                action_name=o.get("action_name"),
                risk=RiskLevel(o["risk"]),
            )
            for o in raw.get("target_overrides", [])
        ]

    def check_reachable(self, url: str) -> None:
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

    def classify_risk(self, action_type: str, url: Optional[str] = None, target_name: Optional[str] = None) -> RiskLevel:
        path = urlparse(url).path if url is not None else None

        for override in self.target_overrides:
            path_matches = override.path_pattern is not None and path is not None and override.path_pattern.match(path)
            name_matches = override.action_name is not None and target_name is not None and override.action_name == target_name
            if path_matches or name_matches:
                return override.risk

        return self.action_risk.get(action_type, RiskLevel.REQUIRES_APPROVAL)

    def enforce(self, action_type: str, url: Optional[str] = None, target_name: Optional[str] = None) -> RiskLevel:
        if url is not None:
            self.check_reachable(url)

        risk = self.classify_risk(action_type, url, target_name)
        if risk == RiskLevel.BLOCKED:
            raise PolicyViolation(f"Action '{action_type}' targeting {url or target_name} is blocked by policy")
        return risk