"""
A minimal in-memory Surface implementation used only for testing the
replay engine's decision logic (outcome detection, postconditions,
approval gating, input validation) without needing a real browser. It
simulates just enough of the balance-lookup flow's states to exercise
those decisions.

This is deliberately not a general-purpose fake -- it interprets targets
by inspecting the first locator strategy's kind, which is enough for the
capability we're testing against but not meant to be a full WebSurface
substitute.
"""
from __future__ import annotations

from src.surfaces.base import Action, ActResult, Observation, Surface

FAKE_MEMBERS = {
    "12345": {"name": "Jordan Ellis", "savings_balance": "$4,210.55"},
}


class FakeSurface(Surface):
    def __init__(self):
        self.page_state = "blank"  # "search" | "detail" | "not_found"
        self.typed_member_id = None
        self.url = "http://localhost:9999/blank"

    def observe(self) -> Observation:
        if self.page_state == "search":
            tree = 'textbox "Member ID"\nbutton "Search"'
        elif self.page_state == "not_found":
            tree = 'text: No member matching\ntextbox "Member ID"\nbutton "Search"'
        elif self.page_state == "detail":
            balance = FAKE_MEMBERS[self.typed_member_id]["savings_balance"]
            tree = f'rowheader "Savings Balance"\ncell "{balance}"'
        else:
            tree = ""
        return Observation(url=self.url, accessibility_tree=tree, screenshot_path=None)

    def act(self, action: Action) -> ActResult:
        if action.type == "navigate":
            self.page_state = "search"
            self.url = action.value
            return ActResult(success=True, resolved_via="navigate")

        if action.type == "type":
            self.typed_member_id = action.value
            return ActResult(success=True, resolved_via="RoleNameLocator")

        if action.type == "click":
            if self.typed_member_id in FAKE_MEMBERS:
                self.page_state = "detail"
            else:
                self.page_state = "not_found"
            return ActResult(success=True, resolved_via="RoleNameLocator")

        if action.type == "read_text":
            if self.page_state == "detail":
                balance = FAKE_MEMBERS[self.typed_member_id]["savings_balance"]
                return ActResult(success=True, resolved_via="RowLabelLocator", extracted_text=balance)
            return ActResult(success=False, error="No strategy resolved this target")

        return ActResult(success=False, error=f"Unknown action: {action.type}")

    def current_url(self) -> str:
        return self.url

    def element_visible(self, target) -> bool:
        strategy = target.strategies[0]
        if strategy.kind == "row_label":
            return self.page_state == "detail" and strategy.row_label == "Savings Balance"
        if strategy.kind == "role_name":
            if strategy.role == "textbox" and strategy.name == "Member ID":
                return self.page_state in ("search", "not_found")
        return False