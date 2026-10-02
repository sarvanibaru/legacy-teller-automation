"""
The real deal: replays the actual saved artifact (artifacts/member_read_savings_balance.json)
against the real mock app through WebSurface, with the ReplayEngine making
every decision -- no LLM anywhere in this file. Reuses the same
live-server-in-a-thread pattern as test_web_surface_live.py.
"""
import sys
import threading
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

sys.path.insert(0, str(Path(__file__).parent.parent / "mock_app"))

from src.artifact.capability import Capability
from src.evidence.logger import EvidenceLogger
from src.replay.engine import ReplayEngine
from src.safety.policy import PolicyEngine
from src.surfaces.base import Action
from src.surfaces.targeting import TargetDescriptor
from src.surfaces.web_surface import WebSurface
from data import VALID_PASSWORD, VALID_USERNAME 

TEST_PORT = 5098
BASE_URL = f"http://localhost:{TEST_PORT}"


@pytest.fixture(scope="module")
def live_mock_app():
    import app as mock_app_module

    server = make_server("localhost", TEST_PORT, mock_app_module.app)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    time.sleep(0.3)

    yield BASE_URL

    server.shutdown()


@pytest.fixture
def authenticated_surface(live_mock_app, tmp_path):
    """Replay assumes an already-authenticated session (see the design
    note in src/artifact/examples.py) -- so this fixture logs in once,
    exactly like a platform-managed session would, before handing the
    surface to the replay engine."""
    policy = PolicyEngine("policy.yaml")
    policy.allowed_origins.append(BASE_URL)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        surface = WebSurface(page, policy, screenshot_dir=tmp_path)

        surface.act(Action(type="navigate", value=f"{BASE_URL}/login"))
        surface.act(Action(
            type="type",
            target=TargetDescriptor.by_role("textbox", "Username"),
            value=VALID_USERNAME,
        ))
        surface.act(Action(
            type="type",
            target=TargetDescriptor.by_role("textbox", "Password"),
            value=VALID_PASSWORD,
        ))
        surface.act(Action(type="click", target=TargetDescriptor.by_role("button", "Log In")))

        yield surface
        browser.close()


def load_capability() -> Capability:
    path = Path("artifacts/member_read_savings_balance.json")
    return Capability.model_validate_json(path.read_text())


def test_replay_real_artifact_against_real_app_valid_member(authenticated_surface, tmp_path):
    capability = load_capability()
    logger = EvidenceLogger(run_id="replay_valid_member", output_dir=tmp_path)
    engine = ReplayEngine(surface=authenticated_surface, base_url=BASE_URL, evidence_logger=logger)

    result = engine.replay(capability, inputs={"memberId": "12345"}, allow_draft=True)

    assert result.status == "success"
    assert result.outputs["savingsBalance"] == 4210.55


def test_replay_real_artifact_against_real_app_unknown_member(authenticated_surface, tmp_path):
    capability = load_capability()
    logger = EvidenceLogger(run_id="replay_unknown_member", output_dir=tmp_path)
    engine = ReplayEngine(surface=authenticated_surface, base_url=BASE_URL, evidence_logger=logger)

    result = engine.replay(capability, inputs={"memberId": "99999"}, allow_draft=True)

    assert result.status == "business_outcome"
    assert result.outcome_code == "MEMBER_NOT_FOUND"