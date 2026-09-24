from __future__ import annotations

from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from src.safety.policy import PolicyEngine, PolicyViolation
from src.surfaces.base import Action, ActResult, Observation, Surface
from src.surfaces.targeting import (
    RoleNameLocator,
    RowLabelLocator,
    TargetDescriptor,
    TextExactLocator,
)


class WebSurface(Surface):
    def __init__(
        self,
        page: Page,
        policy: PolicyEngine,
        screenshot_dir: str | Path = "evidence/tmp",
    ):
        self.page = page
        self.policy = policy
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    # ---------- observation ----------

    def observe(self) -> Observation:
        tree = self._render_accessibility_tree()
        screenshot_path = self._take_screenshot()
        return Observation(
            url=self.page.url,
            accessibility_tree=tree,
            screenshot_path=screenshot_path,
        )

    def _render_accessibility_tree(self) -> str:
        """Playwright's modern aria_snapshot() returns the accessibility
        tree as a readable YAML-style string directly -- this is what gets
        shown to the LLM, and it's dramatically shorter and more meaningful
        than raw HTML for a legacy page."""
        return self.page.locator("body").aria_snapshot()

    def _take_screenshot(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = self.screenshot_dir / f"{timestamp}.png"
        self.page.screenshot(path=str(path))
        return str(path)

    # ---------- action ----------

    def act(self, action: Action) -> ActResult:
        try:
            if action.type == "navigate":
                return self._do_navigate(action)
            elif action.type == "click":
                return self._do_click(action)
            elif action.type == "type":
                return self._do_type(action)
            elif action.type == "read_text":
                return self._do_read_text(action)
            else:
                return ActResult(success=False, error=f"Unknown action type: {action.type}")
        except PolicyViolation as e:
            return ActResult(success=False, error=f"PolicyViolation: {e}")
        except PlaywrightTimeoutError as e:
            return ActResult(success=False, error=f"Timed out resolving target: {e}")
        except Exception as e:
            return ActResult(success=False, error=f"{type(e).__name__}: {e}")

    def _do_navigate(self, action: Action) -> ActResult:
        url = action.value
        self.policy.enforce("navigate", url=url)
        self.page.goto(url)
        return ActResult(success=True, resolved_via="navigate")

    def _do_click(self, action: Action) -> ActResult:
        self.policy.enforce("click", url=self.page.url)
        locator, strategy_name = self._resolve(action.target)
        locator.click()
        return ActResult(success=True, resolved_via=strategy_name)

    def _do_type(self, action: Action) -> ActResult:
        self.policy.enforce("type", url=self.page.url)
        locator, strategy_name = self._resolve(action.target)
        locator.fill(action.value or "")
        return ActResult(success=True, resolved_via=strategy_name)

    def _do_read_text(self, action: Action) -> ActResult:
        self.policy.enforce("read_text", url=self.page.url)
        locator, strategy_name = self._resolve(action.target)
        text = locator.inner_text()
        return ActResult(success=True, resolved_via=strategy_name, extracted_text=text)

    # ---------- targeting ----------

    def _resolve(self, target: TargetDescriptor):
        """Tries each strategy in order, returns the first that resolves
        to a visible element, along with which strategy it was. That
        second piece is what makes drift observable later -- if replay
        keeps needing strategy 2 instead of strategy 1, that's worth
        knowing."""
        if target is None:
            raise ValueError("This action requires a target")

        last_error = None
        for strategy in target.strategies:
            try:
                locator = self._locator_for_strategy(strategy)
                locator.wait_for(state="visible", timeout=3000)
                return locator, type(strategy).__name__
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(f"No strategy resolved this target. Last error: {last_error}")

    def _locator_for_strategy(self, strategy):
        if isinstance(strategy, RoleNameLocator):
            return self.page.get_by_role(strategy.role, name=strategy.name)
        elif isinstance(strategy, RowLabelLocator):
            # Anchoring on "row" by name is fragile in nested-table legacy
            # markup: a row's accessible name can absorb its ancestors'
            # text too, so multiple rows can match the same substring.
            # Anchoring on the specific rowheader, then walking to its
            # parent row, then finding that row's cell, stays unambiguous.
            rowheader = self.page.get_by_role(
                "rowheader", name=strategy.row_label, exact=True
            )
            row = rowheader.locator("xpath=..")
            return row.get_by_role("cell")
        elif isinstance(strategy, TextExactLocator):
            return self.page.get_by_text(strategy.text, exact=True)
        else:
            raise ValueError(f"Unrecognized locator strategy: {strategy}")