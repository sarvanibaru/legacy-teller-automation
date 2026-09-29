"""
Evaluates a Condition (from src/artifact/conditions.py) against the
current state of a live Surface. This is the one place all four uses of
Condition -- step postconditions, outcome detectors, recovery triggers,
and the final checkpoint -- actually get checked.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from src.artifact.conditions import Condition
from src.surfaces.base import Observation, Surface


def evaluate_condition(condition: Condition, observation: Observation, surface: Surface) -> bool:
    if condition.kind == "text_present":
        return condition.pattern in observation.accessibility_tree

    elif condition.kind == "url_matches":
        path = urlparse(observation.url).path
        return re.match(condition.pattern, path) is not None

    elif condition.kind == "element_visible":
        return surface.element_visible(condition.target)

    elif condition.kind == "all_of":
        return all(
            evaluate_condition(sub, observation, surface)
            for sub in condition.conditions
        )

    else:
        raise ValueError(f"Unknown condition kind: {condition.kind}")