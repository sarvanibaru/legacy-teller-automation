"""
Closes the full loop with zero manually-authored artifacts: reads the
real discovery trace from the live agent run, emits a genuine Capability
from it, saves that artifact, and replays it deterministically against
the real mock app.

Also deliberately replays it with an unknown member ID. The emitted
artifact only ever observed the happy path during discovery, so it has no
MEMBER_NOT_FOUND outcome declared -- this is expected to surface as a
hard failure rather than a clean business outcome, which is an honest
demonstration of why a draft capability needs human review (or a second,
adversarial discovery run) before promotion to "approved", not a bug in
the replay engine.

Requires the mock app running separately:
    cd mock_app && python3 app.py

Run from the repo root:
    python3 scripts/emit_and_replay_from_discovery.py
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from src.agent.loop import DiscoveryResult, DiscoveryStepRecord
from src.artifact.capability import AppProfile, Capability
from src.artifact.emitter import build_capability_from_trace
from src.evidence.logger import EvidenceLogger
from src.replay.engine import ReplayEngine
from src.safety.policy import PolicyEngine
from src.surfaces.base import Action
from src.surfaces.targeting import TargetDescriptor
from src.surfaces.web_surface import WebSurface

sys.path.insert(0, str(Path(__file__).parent.parent / "mock_app"))
from data import VALID_PASSWORD, VALID_USERNAME  

BASE_URL = "http://localhost:5001"
TRACE_PATH = Path("evidence/discovery_balance_lookup/discovery_trace.json")
EMITTED_ARTIFACT_PATH = Path("artifacts/member_read_savings_balance_agent_generated.json")


def load_discovery_result(path: Path) -> DiscoveryResult:
    data = json.loads(path.read_text())
    steps = [DiscoveryStepRecord(**s) for s in data["steps"]]
    return DiscoveryResult(
        status=data["status"],
        goal=data["goal"],
        steps=steps,
        outputs=data.get("outputs"),
        success=data.get("success"),
        starting_url=data.get("starting_url"),
    )


def login(surface):
    surface.act(Action(type="navigate", value=f"{BASE_URL}/login"))
    surface.act(Action(type="type", target=TargetDescriptor.by_role("textbox", "Username"), value=VALID_USERNAME))
    surface.act(Action(type="type", target=TargetDescriptor.by_role("textbox", "Password"), value=VALID_PASSWORD))
    surface.act(Action(type="click", target=TargetDescriptor.by_role("button", "Log In")))


def main():
    if not TRACE_PATH.exists():
        print(f"ERROR: {TRACE_PATH} not found. Run scripts/run_discovery.py first.")
        return

    discovery_result = load_discovery_result(TRACE_PATH)

    capability = build_capability_from_trace(
        discovery_result,
        capability_id="member.read_savings_balance.agent_generated",
        description="Agent-discovered: look up a member and read their savings balance.",
        app_profile=AppProfile(vendor="MockBank", product="CoreTeller", version="1.0-mock"),
    )

    EMITTED_ARTIFACT_PATH.parent.mkdir(exist_ok=True)
    EMITTED_ARTIFACT_PATH.write_text(capability.model_dump_json(indent=2))
    print(f"Emitted artifact saved to {EMITTED_ARTIFACT_PATH}")
    print(f"  inputs:  {[i.name for i in capability.inputs]}")
    print(f"  outputs: {[o.name for o in capability.outputs]}")
    print(f"  steps:   {len(capability.steps)}")
    print(f"  outcomes declared: {len(capability.outcomes)} (expected: 0, see docstring)")

    policy = PolicyEngine("policy.yaml")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        surface = WebSurface(page, policy, screenshot_dir="evidence/replay_agent_generated_artifact")
        login(surface)

        logger = EvidenceLogger(run_id="replay_agent_generated_valid", output_dir="evidence/replay_agent_generated_artifact")
        engine = ReplayEngine(surface=surface, base_url=BASE_URL, evidence_logger=logger)
        result = engine.replay(capability, inputs={"memberId": "12345"}, allow_draft=True)
        logger.close()
        print(f"\n=== Replay with valid member (12345) ===")
        print("status:", result.status)
        print("outputs:", result.outputs)

        logger2 = EvidenceLogger(run_id="replay_agent_generated_unknown", output_dir="evidence/replay_agent_generated_artifact")
        engine2 = ReplayEngine(surface=surface, base_url=BASE_URL, evidence_logger=logger2)
        result2 = engine2.replay(capability, inputs={"memberId": "99999"}, allow_draft=True)
        logger2.close()
        print(f"\n=== Replay with unknown member (99999) ===")
        print("status:", result2.status)
        print("(expected: 'failed', since this draft artifact never learned MEMBER_NOT_FOUND)")
        print("failed at step:", result2.step_id)
        print("expected:", result2.expected)
        print("observed:", result2.observed)
        print("error:", result2.error)

        browser.close()


if __name__ == "__main__":
    main()