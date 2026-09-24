import json

from src.evidence.logger import EvidenceLogger


def test_log_writes_valid_json_line(tmp_path):
    logger = EvidenceLogger(run_id="test_run", output_dir=tmp_path)
    logger.log("step_started", step_id="s1", action="click")
    logger.close()

    lines = logger.log_path.read_text().strip().splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["event_type"] == "step_started"
    assert record["step_id"] == "s1"
    assert record["run_id"] == "test_run"
    assert "timestamp" in record


def test_multiple_events_append_as_separate_lines(tmp_path):
    logger = EvidenceLogger(run_id="test_run", output_dir=tmp_path)
    logger.log("step_started", step_id="s1")
    logger.log("step_completed", step_id="s1", outcome="success")
    logger.close()

    lines = logger.log_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "step_started"
    assert json.loads(lines[1])["event_type"] == "step_completed"


def test_sensitive_fields_are_redacted_before_reaching_disk(tmp_path):
    logger = EvidenceLogger(run_id="test_run", output_dir=tmp_path)
    logger.log("form_filled", field_name="password", password="hunter2")
    logger.close()

    raw_content = logger.log_path.read_text()
    assert "hunter2" not in raw_content


def test_context_manager_closes_file(tmp_path):
    with EvidenceLogger(run_id="test_run", output_dir=tmp_path) as logger:
        logger.log("step_started", step_id="s1")
    # file should be closed and readable afterward without issue
    assert logger.log_path.exists()
