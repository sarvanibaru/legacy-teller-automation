from src.artifact.examples import build_balance_lookup_capability
from src.evidence.logger import EvidenceLogger
from src.replay.engine import ReplayEngine
from fake_surface import FakeSurface


def make_engine(tmp_path):
    surface = FakeSurface()
    logger = EvidenceLogger(run_id="test_replay", output_dir=tmp_path)
    engine = ReplayEngine(surface=surface, base_url="http://localhost:9999", evidence_logger=logger)
    return engine


def test_replay_succeeds_for_valid_member(tmp_path):
    engine = make_engine(tmp_path)
    capability = build_balance_lookup_capability()

    result = engine.replay(capability, inputs={"memberId": "12345"}, allow_draft=True)

    assert result.status == "success"
    assert result.outputs["savingsBalance"] == 4210.55


def test_replay_reports_business_outcome_for_unknown_member(tmp_path):
    engine = make_engine(tmp_path)
    capability = build_balance_lookup_capability()

    result = engine.replay(capability, inputs={"memberId": "99999"}, allow_draft=True)

    assert result.status == "business_outcome"
    assert result.outcome_code == "MEMBER_NOT_FOUND"
    assert result.outcome_success is False


def test_replay_refuses_draft_capability_without_explicit_opt_in(tmp_path):
    engine = make_engine(tmp_path)
    capability = build_balance_lookup_capability()
    assert capability.approval_state == "draft"

    result = engine.replay(capability, inputs={"memberId": "12345"}, allow_draft=False)

    assert result.status == "failed"
    assert "not approved" in result.error.lower() or "draft" in result.error.lower()


def test_replay_reports_clean_failure_for_missing_required_input(tmp_path):
    engine = make_engine(tmp_path)
    capability = build_balance_lookup_capability()

    result = engine.replay(capability, inputs={}, allow_draft=True)

    assert result.status == "failed"
    assert "memberId" in result.error


def test_replay_reports_clean_failure_for_input_violating_pattern(tmp_path):
    engine = make_engine(tmp_path)
    capability = build_balance_lookup_capability()

    result = engine.replay(capability, inputs={"memberId": "not-a-number"}, allow_draft=True)

    assert result.status == "failed"
    assert "pattern" in result.error.lower()