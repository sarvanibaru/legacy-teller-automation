"""
THE genuine LLM-driven discovery run the brief requires. Uses your real
Anthropic API key (from .env) against the real mock app running at
localhost:5001.

Requires the mock app running separately:
    cd mock_app && python3 app.py

Run from the repo root:
    python3 scripts/run_discovery.py

Runs headful (a visible Chromium window) so you can watch the agent
actually operate the app in real time -- this is the moment the whole
project has been building toward.
"""
import dataclasses
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from src.agent.decision_client import AnthropicDecisionClient
from src.agent.loop import DiscoveryAgent
from src.evidence.logger import EvidenceLogger
from src.safety.policy import PolicyEngine
from src.safety.redaction import redact_value
from src.surfaces.base import Action
from src.surfaces.targeting import TargetDescriptor
from src.surfaces.web_surface import WebSurface

# Import the mock app's own credential constants rather than retyping them
# here -- mock_app/data.py is the single source of truth, so a credential
# change there can never silently drift out of sync with this script
sys.path.insert(0, str(Path(__file__).parent.parent / "mock_app"))
from data import VALID_USERNAME, VALID_PASSWORD  

BASE_URL = "http://localhost:5001"
GOAL = "Look up member 12345 and read their current savings balance."
RUN_ID = "discovery_balance_lookup"


def login(surface):
    """The harness handles authentication -- the agent never sees
    credentials, matching the same assumption a saved capability makes.
    Also note: no EvidenceLogger is constructed until after this returns,
    so these credentials never touch any log or evidence file either."""
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


def main():
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not found. Check your .env file.")
        return

    evidence_dir = Path("evidence") / RUN_ID
    evidence_dir.mkdir(parents=True, exist_ok=True)

    policy = PolicyEngine("policy.yaml")
    logger = EvidenceLogger(run_id=RUN_ID, output_dir=evidence_dir)
    decision_client = AnthropicDecisionClient(api_key=api_key, model=model)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=400)
        page = browser.new_page()
        surface = WebSurface(page, policy, screenshot_dir=evidence_dir)

        login(surface)

        agent = DiscoveryAgent(surface=surface, decision_client=decision_client, evidence_logger=logger)

        print(f"\n=== Starting discovery run ===\nGoal: {GOAL}\nModel: {model}\n")
        result = agent.run(goal=GOAL)

        print(f"\n=== Result ===")
        print("status:", result.status)
        print("success:", result.success)
        print("outputs:", result.outputs)
        print(f"steps taken: {len(result.steps)}")

        # Save the full trace, redacted, as a real deliverable -- this is
        # what the artifact emitter (next step) will read to build a
        # Capability from what the agent actually did.
        trace_dict = redact_value(dataclasses.asdict(result))
        trace_path = evidence_dir / "discovery_trace.json"
        trace_path.write_text(json.dumps(trace_dict, indent=2))
        print(f"\nFull trace saved to {trace_path}")

        logger.close()
        browser.close()


if __name__ == "__main__":
    main()