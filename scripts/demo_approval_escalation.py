"""
LIVE DEMO 1: approval-gated escalation.

Replays the sub-account confirmation capability. Its final step --
clicking "Confirm and Open Account" -- is genuinely classified
requires_approval by policy. When the replay engine reaches it, it will
pause and wait for you to open the operator console and click Approve
(or Reject, to see that path instead).

Requires the mock app running separately:
    cd mock_app && python3 app.py

Run from the repo root:
    python3 scripts/demo_approval_escalation.py

Then, when the terminal tells you to, open:
    http://localhost:5050
in your browser and click Approve (or Reject).
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from src.artifact.capability import Capability
from src.escalation.intervention import EscalationManager
from src.escalation.operator_app import run_operator_app_in_background
from src.escalation.session_controller import SessionController
from src.evidence.logger import EvidenceLogger
from src.replay.engine import ReplayEngine
from src.safety.policy import PolicyEngine
from src.surfaces.base import Action
from src.surfaces.escalating_surface import EscalatingSurface
from src.surfaces.targeting import TargetDescriptor
from src.surfaces.web_surface import WebSurface

sys.path.insert(0, str(Path(__file__).parent.parent / "mock_app"))
from data import VALID_PASSWORD, VALID_USERNAME  # noqa: E402

BASE_URL = "http://localhost:5001"
ARTIFACT_PATH = Path("artifacts/member_open_sub_account_confirm_demo.json")
EVIDENCE_DIR = Path("evidence/demo_approval_escalation")
OPERATOR_PORT = 5050


def login_and_navigate_to_member(surface, member_id: str):
    surface.act(Action(type="navigate", value=f"{BASE_URL}/login"))
    surface.act(Action(type="type", target=TargetDescriptor.by_role("textbox", "Username"), value=VALID_USERNAME))
    surface.act(Action(type="type", target=TargetDescriptor.by_role("textbox", "Password"), value=VALID_PASSWORD))
    surface.act(Action(type="click", target=TargetDescriptor.by_role("button", "Log In")))
    surface.act(Action(type="navigate", value=f"{BASE_URL}/member/{member_id}"))


def main():
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    capability = Capability.model_validate_json(ARTIFACT_PATH.read_text())

    policy = PolicyEngine("policy.yaml")
    session = SessionController()
    escalation = EscalationManager(session=session, evidence_dir=EVIDENCE_DIR / "interventions")

    print(f"\nStarting operator console at http://localhost:{OPERATOR_PORT}")
    operator_server = run_operator_app_in_background(escalation, port=OPERATOR_PORT)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        raw_surface = WebSurface(page, policy, screenshot_dir=EVIDENCE_DIR)

        print("Logging in and navigating to member 12345...")
        login_and_navigate_to_member(raw_surface, "12345")

        escalating_surface = EscalatingSurface(
            inner=raw_surface,
            policy=policy,
            escalation=escalation,
            capability_id=capability.capability_id,
        )

        logger = EvidenceLogger(run_id="demo_approval_escalation", output_dir=EVIDENCE_DIR)
        engine = ReplayEngine(surface=escalating_surface, base_url=BASE_URL, evidence_logger=logger)

        print("\n" + "=" * 70)
        print("Replaying the sub-account capability. It WILL pause at the final")
        print("step for your approval.")
        print(f"\n  >>> Open http://localhost:{OPERATOR_PORT} now and click Approve or Reject <<<\n")
        print("=" * 70 + "\n")

        result = engine.replay(capability, inputs={}, allow_draft=True)

        print("\n=== Result ===")
        print("status:", result.status)
        if result.status == "failed":
            print("step_id:", result.step_id)
            print("error:", result.error)

        logger.close()
        browser.close()

    operator_server.shutdown()
    print(f"\nEvidence saved to {EVIDENCE_DIR}/")


if __name__ == "__main__":
    main()