import threading
import time

from fake_surface import FakeSurface

from src.artifact.capability import AppProfile, Capability
from src.artifact.conditions import ElementVisibleCondition
from src.artifact.io_spec import InputParam, OutputField
from src.artifact.step import Step
from src.artifact.values import ParamValue
from src.escalation.intervention import EscalationManager
from src.escalation.session_controller import SessionController
from src.evidence.logger import EvidenceLogger
from src.replay.engine import ReplayEngine
from src.surfaces.targeting import TargetDescriptor


def make_minimal_capability():
    """Deliberately has no declared outcomes, so a failed read_text
    reaches the genuine hard-failure path rather than being intercepted
    earlier as a business outcome -- isolating the escalation-retry
    behavior specifically."""
    return Capability(
        capability_id="test.minimal_lookup",
        description="test",
        app_profile=AppProfile(vendor="Test", product="Test"),
        approval_state="draft",
        inputs=[InputParam(name="memberId", type="string")],
        outputs=[OutputField(name="savingsBalance", type="number", extract_from_step="s3", parse="currency")],
        steps=[
            Step(id="s1", action="type", target=TargetDescriptor.by_role("textbox", "Member ID"), value=ParamValue(param="memberId")),
            Step(id="s2", action="click", target=TargetDescriptor.by_role("button", "Search")),
            Step(id="s3", action="read_text", target=TargetDescriptor.by_row_label("Savings Balance")),
        ],
        outcomes=[],
        recoveries=[],
        checkpoint=ElementVisibleCondition(target=TargetDescriptor.by_row_label("Savings Balance")),
    )


def test_replay_escalates_on_hard_failure_and_succeeds_after_human_fixes_it(tmp_path):
    surface = FakeSurface()
    session = SessionController()
    escalation = EscalationManager(session=session, evidence_dir=tmp_path)
    logger = EvidenceLogger(run_id="test", output_dir=tmp_path)
    engine = ReplayEngine(surface=surface, base_url="http://localhost:9999", evidence_logger=logger, escalation=escalation)
    capability = make_minimal_capability()

    def simulate_human_fixing_it():
        while session.current_owner != "human":
            time.sleep(0.05)
        # The read_text step failed because memberId=99999 isn't a known
        # member -- simulate a human manually finding the right member
        # live and landing on their detail page.
        surface.typed_member_id = "12345"
        surface.page_state = "detail"
        session.resolve(approved=True, note="found the member manually")

    threading.Thread(target=simulate_human_fixing_it).start()

    result = engine.replay(capability, inputs={"memberId": "99999"}, allow_draft=True)

    assert result.status == "success"
    assert result.outputs["savingsBalance"] == 4210.55


def test_replay_reports_hard_failure_if_human_declines(tmp_path):
    surface = FakeSurface()
    session = SessionController()
    escalation = EscalationManager(session=session, evidence_dir=tmp_path)
    logger = EvidenceLogger(run_id="test2", output_dir=tmp_path)
    engine = ReplayEngine(surface=surface, base_url="http://localhost:9999", evidence_logger=logger, escalation=escalation)
    capability = make_minimal_capability()

    def simulate_human_declining():
        while session.current_owner != "human":
            time.sleep(0.05)
        session.resolve(approved=False, note="can't fix this, genuinely broken")

    threading.Thread(target=simulate_human_declining).start()

    result = engine.replay(capability, inputs={"memberId": "99999"}, allow_draft=True)

    assert result.status == "failed"
    assert result.step_id == "s3"