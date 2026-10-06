"""
Builds and saves the hand-written sub-account confirmation capability --
the one used to demonstrate the approval-gate escalation, since its final
step is genuinely classified requires_approval by policy.

Run from the repo root:
    python3 scripts/build_subaccount_artifact.py
"""
from pathlib import Path

from src.artifact.capability import Capability
from src.artifact.examples import build_subaccount_confirm_capability


def main():
    capability = build_subaccount_confirm_capability()

    output_dir = Path("artifacts")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "member_open_sub_account_confirm_demo.json"

    output_path.write_text(capability.model_dump_json(indent=2))
    print(f"Wrote {output_path}")

    restored = Capability.model_validate_json(output_path.read_text())
    assert restored.capability_id == capability.capability_id
    assert len(restored.steps) == len(capability.steps)
    print("Round-trip validation OK")


if __name__ == "__main__":
    main()