import argparse
from pathlib import Path

from evidence.integrity import MISMATCH, verify_evidence


EXAMPLE_ROOT = Path(__file__).resolve().parent.parent
CONTROL_PATH = EXAMPLE_ROOT / "controls" / "ACP-001-03.yaml"
ENVIRONMENT_PATH = EXAMPLE_ROOT / "sample-data" / "identity-environment.json"
VALIDATOR_PATH = EXAMPLE_ROOT / "validation" / "validator.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Structured Control Validation Evidence integrity."
    )
    parser.add_argument(
        "--evidence-directory",
        type=Path,
        default=EXAMPLE_ROOT / "generated-evidence",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evidence_paths = sorted(args.evidence_directory.glob("*.json"))
    if not evidence_paths:
        print("evidence_directory | MISMATCH | mismatches: no_evidence_records")
        raise SystemExit(1)

    mismatch_found = False
    for evidence_path in evidence_paths:
        try:
            verification = verify_evidence(
                evidence_path,
                evidence_path.with_suffix(".json.sha256"),
                CONTROL_PATH,
                ENVIRONMENT_PATH,
                VALIDATOR_PATH,
            )
        except Exception as error:
            print(
                f"{evidence_path.name} | MISMATCH | "
                f"mismatches: verification_error ({error})"
            )
            mismatch_found = True
            continue
        mismatch_found = mismatch_found or verification.status == MISMATCH
        mismatches = ", ".join(verification.mismatched_components) or "none"
        print(f"{evidence_path.name} | {verification.status} | mismatches: {mismatches}")

    if mismatch_found:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
