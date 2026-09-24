"""
Runs the mock Flask app in a background thread so WebSurface can be tested
against a real live server, without requiring the developer to start it
manually in a separate terminal first.
"""
import sys
import threading
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

sys.path.insert(0, str(Path(__file__).parent.parent / "mock_app"))

from src.safety.policy import PolicyEngine
from src.surfaces.base import Action
from src.surfaces.targeting import TargetDescriptor
from src.surfaces.web_surface import WebSurface

TEST_PORT = 5099
BASE_URL = f"http://localhost:{TEST_PORT}"


@pytest.fixture(scope="module")
def live_mock_app():
    import app as mock_app_module  # the Flask app object, imported from mock_app/app.py

    server = make_server("localhost", TEST_PORT, mock_app_module.app)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    time.sleep(0.3)  # give the server a moment to actually start listening

    yield BASE_URL

    server.shutdown()


@pytest.fixture
def surface(live_mock_app, tmp_path):
    policy = PolicyEngine("policy.yaml")
    # The test server runs on a different port than policy.yaml's
    # allowlist expects, so we widen it for this test only.
    policy.allowed_origins.append(BASE_URL)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        yield WebSurface(page, policy, screenshot_dir=tmp_path)
        browser.close()


def _login(surface):
    surface.act(Action(type="navigate", value=f"{BASE_URL}/login"))
    surface.act(Action(
        type="type",
        target=TargetDescriptor.by_role("textbox", "Username"),
        value="user1",
    ))
    surface.act(Action(
        type="type",
        target=TargetDescriptor.by_role("textbox", "Password"),
        value="password123",
    ))
    surface.act(Action(type="click", target=TargetDescriptor.by_role("button", "Log In")))


def test_login_and_read_savings_balance(surface):
    _login(surface)

    surface.act(Action(
        type="type",
        target=TargetDescriptor.by_role("textbox", "Member ID"),
        value="12345",
    ))
    surface.act(Action(type="click", target=TargetDescriptor.by_role("button", "Search")))

    result = surface.act(Action(
        type="read_text",
        target=TargetDescriptor.by_row_label("Savings Balance"),
    ))

    assert result.success
    assert result.resolved_via == "RowLabelLocator"
    assert result.extracted_text == "$4210.55"


def test_member_not_found_shows_message_without_crashing(surface):
    _login(surface)

    surface.act(Action(
        type="type",
        target=TargetDescriptor.by_role("textbox", "Member ID"),
        value="99999",
    ))
    result = surface.act(Action(type="click", target=TargetDescriptor.by_role("button", "Search")))

    assert result.success  # the click itself succeeds; the app just shows "not found"
    obs = surface.observe()
    assert "No member matching" in obs.accessibility_tree