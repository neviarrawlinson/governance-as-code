import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from evidence.generator import generate_evidence_records, write_evidence_records
from evidence.integrity import (
    build_source_integrity,
    build_source_integrity_from_bytes,
    get_repository_commit,
)
from validation.validator import evaluate_environment


EXAMPLE_ROOT = Path(__file__).resolve().parent.parent
CONTROL_PATH = EXAMPLE_ROOT / "controls" / "ACP-001-03.yaml"
ENVIRONMENT_PATH = EXAMPLE_ROOT / "sample-data" / "identity-environment.json"
VALIDATOR_PATH = EXAMPLE_ROOT / "validation" / "validator.py"
REPOSITORY_ROOT = EXAMPLE_ROOT.parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Structured Control Validation Evidence for ACP-001-03."
    )
    parser.add_argument(
        "--evaluation-date",
        type=date.fromisoformat,
        required=True,
        help="Evaluation date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=EXAMPLE_ROOT / "generated-evidence",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    control_bytes = CONTROL_PATH.read_bytes()
    environment_bytes = ENVIRONMENT_PATH.read_bytes()
    validator_bytes = VALIDATOR_PATH.read_bytes()
    integrity = build_source_integrity_from_bytes(
        control_bytes, environment_bytes, validator_bytes
    )
    control = yaml.safe_load(control_bytes)
    environment = json.loads(environment_bytes)
    validation_results = evaluate_environment(
        control, environment, args.evaluation_date
    )
    if integrity != build_source_integrity(
        CONTROL_PATH, ENVIRONMENT_PATH, VALIDATOR_PATH
    ):
        raise RuntimeError("Referenced source files changed during evidence generation")
    records = generate_evidence_records(
        control,
        environment,
        validation_results,
        args.evaluation_date,
        datetime.now(timezone.utc),
        integrity,
        get_repository_commit(REPOSITORY_ROOT),
    )
    paths = write_evidence_records(records, args.output_directory)

    for record, path in zip(records, paths, strict=True):
        print(
            f"{record['subject']['account_id']} | "
            f"{record['result']['outcome']} | {path}"
        )


if __name__ == "__main__":
    main()
