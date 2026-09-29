"""
Runs the real replay engine against the real mock app for both a valid
and an invalid member ID, saving permanent evidence (JSONL log +
screenshots) into evidence/ -- this is what gets committed as the
replay-run half of the required discovery-run/replay-run evidence pair.

Requires the mock app running separately at http://localhost:5001
(cd mock_app && python3 app.py).

Run from the repo root:
    python3 scripts/run_replay_evidence.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

from src.artifact.capability import Capability
from src.evidence.logger import EvidenceLogger
from src.replay.engine import ReplayEngine
from src.safety.policy import PolicyEngine
from src.surfaces.base import Action
from src.surfaces.targeting import TargetDescriptor
from src.surfaces.web_surface import WebSurface

BASE_URL = "http://localhost:5001"


def login(surface):
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


def run_one_replay(page, policy, member_id: str, run_id: str):
    evidence_dir = Path("evidence") / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    surface = WebSurface(page, policy, screenshot_dir=evidence_dir)
    login(surface)

    logger = EvidenceLogger(run_id=run_id, output_dir=evidence_dir)
    engine = ReplayEngine(surface=surface, base_url=BASE_URL, evidence_logger=logger)

    capability = Capability.model_validate_json(
        Path("artifacts/member_read_savings_balance.json").read_text()
    )
    result = engine.replay(capability, inputs={"memberId": member_id}, allow_draft=True)
    logger.close()

    print(f"\n=== {run_id} (memberId={member_id}) ===")
    print("status:", result.status)
    print("outputs:", result.outputs)
    print("outcome_code:", result.outcome_code)
    print(f"Evidence saved to {evidence_dir}/")


def main():
    policy = PolicyEngine("policy.yaml")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        run_one_replay(page, policy, "12345", "replay_success")
        run_one_replay(page, policy, "99999", "replay_business_outcome_not_found")

        browser.close()


if __name__ == "__main__":
    main()