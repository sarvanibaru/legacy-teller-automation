"""
LIVE DEMO 2: takeover escalation.

WHAT THIS DEMO PROVES, AND WHAT IT DOESN'T:

This demo exists to prove the MECHANISM works: that a running replay can
genuinely pause mid-step, persist context to disk, hand the live browser
session (not a fresh one) to a human, and resume from exactly where it
stopped once they're done -- the actual plumbing Section 3.6 asks for.

It does NOT claim this is a realistic reason to need a human. The
"member not found" failure here is deliberately engineered: it exploits
a known, documented gap in the agent-generated artifact (it only ever
observed the happy path during discovery, so it never learned
MEMBER_NOT_FOUND as a declared outcome -- see REPORT.md). A properly
curated capability would report this as a clean business outcome, not
fail at all. A genuinely realistic trigger for human takeover would be
something like an unhandled confirmation dialog or an error state the
system has no learned response for -- the mechanism supports that too,
it's just not what's exercised here, since this failure mode is easy to
reproduce reliably on demand.

HOW IT WORKS:

Replays the agent-generated balance-lookup artifact with a member ID
(99999) that doesn't exist, which genuinely fails at the read_text step.
With escalation wired in, that failure pauses for a human takeover
instead of just erroring out. You will:
  1. See the terminal say the replay has paused.
  2. Go to the VISIBLE browser window (not the operator console) and
     manually fix it: navigate to /search, search for member 12345.
  3. Go to the operator console (http://localhost:5050) and click Resume.
  4. Watch the replay retry the failed step and succeed, since the live
     page now genuinely shows the balance.

Requires the mock app running separately:
    cd mock_app && python3 app.py

Run from the repo root:
    python3 scripts/demo_takeover_escalation.py
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
ARTIFACT_PATH = Path("artifacts/member_read_savings_balance_agent_generated.json")
EVIDENCE_DIR = Path("evidence/demo_takeover_escalation")
OPERATOR_PORT = 5050


def login(surface):
    surface.act(Action(type="navigate", value=f"{BASE_URL}/login"))
    surface.act(Action(type="type", target=TargetDescriptor.by_role("textbox", "Username"), value=VALID_USERNAME))
    surface.act(Action(type="type", target=TargetDescriptor.by_role("textbox", "Password"), value=VALID_PASSWORD))
    surface.act(Action(type="click", target=TargetDescriptor.by_role("button", "Log In")))


def main():
    if not ARTIFACT_PATH.exists():
        print(f"ERROR: {ARTIFACT_PATH} not found. Run scripts/emit_and_replay_from_discovery.py first.")
        return

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

        print("Logging in...")
        login(raw_surface)

        escalating_surface = EscalatingSurface(
            inner=raw_surface,
            policy=policy,
            escalation=escalation,
            capability_id=capability.capability_id,
            goal="Look up member 99999 (deliberately unknown) and read their savings balance.",
        )

        logger = EvidenceLogger(run_id="demo_takeover_escalation", output_dir=EVIDENCE_DIR)
        engine = ReplayEngine(
            surface=escalating_surface, base_url=BASE_URL, evidence_logger=logger, escalation=escalation
        )

        print("\n" + "=" * 70)
        print("NOTE: this failure is deliberately engineered (a known gap in a")
        print("draft artifact that never learned MEMBER_NOT_FOUND), chosen because")
        print("it's reliably reproducible -- not a claim that this is a realistic")
        print("reason to need a human. This demo proves the PAUSE/PERSIST/RESUME")
        print("mechanism works on a real browser; see REPORT.md for the caveat.")
        print("-" * 70)
        print("Replaying with memberId=99999 (doesn't exist). This artifact has")
        print("no MEMBER_NOT_FOUND outcome, so it WILL fail and pause for takeover.")
        print("\nWhen it pauses:")
        print("  1. Go to the VISIBLE BROWSER WINDOW (not this terminal).")
        print(f"  2. Manually navigate to {BASE_URL}/search and search for member 12345.")
        print("  3. Confirm you can see their Savings Balance on screen.")
        print(f"  4. Open http://localhost:{OPERATOR_PORT} and click Resume.")
        print("=" * 70 + "\n")

        result = engine.replay(capability, inputs={"memberId": "99999"}, allow_draft=True)

        print("\n=== Result ===")
        print("status:", result.status)
        if result.status == "success":
            print("outputs:", result.outputs)
        elif result.status == "failed":
            print("step_id:", result.step_id)
            print("error:", result.error)

        logger.close()
        browser.close()

    operator_server.shutdown()
    print(f"\nEvidence saved to {EVIDENCE_DIR}/")


if __name__ == "__main__":
    main()