"""
Builds and saves the hand-written balance-lookup capability artifact.
The actual capability definition lives in src/artifact/examples.py so it's
reliably importable from tests too; this script is just the "save it to
disk and confirm it round-trips" runner.

Run from the repo root:
    python3 scripts/build_balance_lookup_artifact.py
"""
from pathlib import Path

from src.artifact.capability import Capability
from src.artifact.examples import build_balance_lookup_capability


def main():
    capability = build_balance_lookup_capability()

    output_dir = Path("artifacts")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "member_read_savings_balance.json"

    output_path.write_text(capability.model_dump_json(indent=2))
    print(f"Wrote {output_path}")

    restored = Capability.model_validate_json(output_path.read_text())
    assert restored.capability_id == capability.capability_id
    assert len(restored.steps) == len(capability.steps)
    assert restored.outcomes[0].code == "MEMBER_NOT_FOUND"
    print("Round-trip validation OK")


if __name__ == "__main__":
    main()