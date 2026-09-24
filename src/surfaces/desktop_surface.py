"""
Not implemented for this project -- see REPORT.md, Section 4
(Heterogeneity & multi-tenant) for the full design reasoning.

The point of this stub is to show that Surface, Action, Observation, and
TargetDescriptor don't need to change at all to support a native desktop
app. Windows exposes UI Automation (UIA), macOS exposes the Accessibility
API -- both expose the same kind of role/name/value tree that
WebSurface._render_accessibility_tree() already produces from Playwright's
accessibility.snapshot(). A RoleNameLocator("button", "Search") means the
same thing whether it resolves against a DOM or a native window.

What would actually change, concretely:
  - observe(): call into UIA (e.g. via `pywinauto` or the `uiautomation`
    package) instead of Playwright, walk its element tree the same way
    _render_accessibility_tree() walks Playwright's, and screenshot the
    active window instead of a page.
  - _locator_for_strategy(): translate RoleNameLocator into a UIA control
    search (control_type + Name property) instead of page.get_by_role().
  - act(): the same four action types (navigate/click/type/read_text) map
    onto UIA operations -- "navigate" becomes "bring window to foreground
    / launch executable" rather than page.goto().

Everything above the Surface interface -- the agent loop, the artifact
schema, the replay engine, the policy engine -- is untouched by this
change. That's the seam this abstraction is designed to prove out.
"""
from __future__ import annotations

from src.surfaces.base import Action, ActResult, Observation, Surface


class DesktopSurface(Surface):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "DesktopSurface is a design stub, not implemented for this "
            "project. See the module docstring and REPORT.md Section 4 "
            "for how it would extend the Surface abstraction."
        )

    def observe(self) -> Observation:
        raise NotImplementedError

    def act(self, action: Action) -> ActResult:
        raise NotImplementedError
