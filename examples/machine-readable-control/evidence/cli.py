import argparse
from datetime import date, datetime, timezone
from pathlib import Path

from evidence.generator import generate_evidence_records, write_evidence_records
from validation.validator import evaluate_environment, load_control, load_environment


EXAMPLE_ROOT = Path(__file__).resolve().parent.parent
CONTROL_PATH = EXAMPLE_ROOT / "controls" / "ACP-001-03.yaml"
ENVIRONMENT_PATH = EXAMPLE_ROOT / "sample-data" / "identity-environment.json"


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
    control = load_control(CONTROL_PATH)
    environment = load_environment(ENVIRONMENT_PATH)
    validation_results = evaluate_environment(
        control, environment, args.evaluation_date
    )
    records = generate_evidence_records(
        control,
        environment,
        validation_results,
        args.evaluation_date,
        datetime.now(timezone.utc),
    )
    paths = write_evidence_records(records, args.output_directory)

    for record, path in zip(records, paths, strict=True):
        print(
            f"{record['subject']['account_id']} | "
            f"{record['result']['outcome']} | {path}"
        )


if __name__ == "__main__":
    main()
