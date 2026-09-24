from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.safety.redaction import redact_value


class EvidenceLogger:
    """
    Writes one JSON object per line (JSONL) to a run-specific log file.
    Every event passes through redaction before it touches disk, so no
    caller needs to remember to redact -- it happens here, once, for
    everything that goes through this class.

    Usage:
        logger = EvidenceLogger(run_id="run_2026_09_23_001")
        logger.log("step_started", step_id="s1", action="click")
        logger.log("step_completed", step_id="s1", outcome="success")
        logger.close()
    """

    def __init__(self, run_id: str, output_dir: str | Path = "evidence/tmp"):
        self.run_id = run_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.output_dir / f"{run_id}.jsonl"
        self._file = open(self.log_path, "a")

    def log(self, event_type: str, **fields) -> dict:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event_type": event_type,
            **fields,
        }
        redacted_record = redact_value(record)
        self._file.write(json.dumps(redacted_record) + "\n")
        self._file.flush()
        return redacted_record

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
