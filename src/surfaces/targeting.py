"""
A TargetDescriptor is a ranked list of ways to find one control. Instead of
a single CSS selector (which breaks the moment markup changes), we try
strategies in order and record which one actually worked. That record is
itself useful: if strategy 1 (role+name) stops resolving and strategy 3
starts being the one that succeeds, that's a drift signal worth logging,
not just a private implementation detail.

Strategies are deliberately ordered from most portable to least:
  1. RoleName   -- works on desktop apps too (accessibility roles exist
                   there), so this is what should resolve in the common
                   case and is the strategy artifacts should prefer.
  2. RowLabel   -- for the common legacy pattern of "a table row whose
                   first cell/header names the field, value is the
                   sibling cell." Common in the row-header markup our
                   mock app's balance display uses.
  3. TextExact  -- last resort: find something by its visible text. Least
                   robust (breaks if copy changes) but always available.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass
class RoleNameLocator:
    role: str    # e.g. "textbox", "button", "link"
    name: str    # the accessible name, e.g. "Member ID"


@dataclass
class RowLabelLocator:
    """Finds the value cell in a row whose row-header text matches
    row_label. Matches the <th scope="row">Savings Balance</th> pattern
    used on the member detail page."""
    row_label: str


@dataclass
class TextExactLocator:
    text: str


Locator = Union[RoleNameLocator, RowLabelLocator, TextExactLocator]


@dataclass
class TargetDescriptor:
    strategies: list[Locator]

    @classmethod
    def by_role(cls, role: str, name: str) -> "TargetDescriptor":
        """Convenience for the common case: role+name only."""
        return cls(strategies=[RoleNameLocator(role=role, name=name)])

    @classmethod
    def by_row_label(cls, row_label: str) -> "TargetDescriptor":
        return cls(strategies=[RowLabelLocator(row_label=row_label)])
