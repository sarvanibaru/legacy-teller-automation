"""
Manual demo -- not a pytest test. Requires the mock app running separately
at http://localhost:5001 (cd mock_app && python3 app.py).

Run from the repo root:
    python3 scripts/demo_web_surface.py

Drives the full balance-lookup flow through WebSurface, printing the
accessibility tree at each step so you can see what the agent will
eventually see, and printing which locator strategy resolved each target.
"""
from playwright.sync_api import sync_playwright

from src.safety.policy import PolicyEngine
from src.surfaces.base import Action
from src.surfaces.targeting import TargetDescriptor
from src.surfaces.web_surface import WebSurface

BASE_URL = "http://localhost:5001"


def main():
    policy = PolicyEngine("policy.yaml")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        page = browser.new_page()
        surface = WebSurface(page, policy)

        print("=== Navigating to login ===")
        surface.act(Action(type="navigate", value=f"{BASE_URL}/login"))
        obs = surface.observe()
        print(obs.accessibility_tree)

        print("\n=== Logging in ===")
        result = surface.act(Action(
            type="type",
            target=TargetDescriptor.by_role("textbox", "Username"),
            value="user1",
        ))
        print("typed username via:", result.resolved_via)

        result = surface.act(Action(
            type="type",
            target=TargetDescriptor.by_role("textbox", "Password"),
            value="password123",
        ))
        print("typed password via:", result.resolved_via)

        result = surface.act(Action(
            type="click",
            target=TargetDescriptor.by_role("button", "Log In"),
        ))
        print("clicked Log In via:", result.resolved_via)

        print("\n=== On search page ===")
        obs = surface.observe()
        print(obs.accessibility_tree)

        print("\n=== Searching for member 12345 ===")
        surface.act(Action(
            type="type",
            target=TargetDescriptor.by_role("textbox", "Member ID"),
            value="12345",
        ))
        surface.act(Action(
            type="click",
            target=TargetDescriptor.by_role("button", "Search"),
        ))

        print("\n=== On member detail page ===")
        obs = surface.observe()
        print(obs.accessibility_tree)

        print("\n=== Reading savings balance ===")
        result = surface.act(Action(
            type="read_text",
            target=TargetDescriptor.by_row_label("Savings Balance"),
        ))
        print("success:", result.success)
        print("resolved via:", result.resolved_via)
        print("extracted text:", result.extracted_text)
        print("error:", result.error)

        browser.close()


if __name__ == "__main__":
    main()