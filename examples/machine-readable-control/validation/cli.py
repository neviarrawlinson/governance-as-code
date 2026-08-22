import argparse
from datetime import date
from pathlib import Path

from validation.validator import evaluate_environment, load_control, load_environment


EXAMPLE_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the synthetic identity environment against ACP-001-03."
    )
    parser.add_argument(
        "--control",
        type=Path,
        default=EXAMPLE_ROOT / "controls" / "ACP-001-03.yaml",
    )
    parser.add_argument(
        "--environment",
        type=Path,
        default=EXAMPLE_ROOT / "sample-data" / "identity-environment.json",
    )
    parser.add_argument(
        "--evaluation-date",
        type=date.fromisoformat,
        required=True,
        help="Evaluation date in YYYY-MM-DD format.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    control = load_control(args.control)
    environment = load_environment(args.environment)
    results = evaluate_environment(control, environment, args.evaluation_date)

    for result in results:
        print(
            f"{result.account_id} | {result.username} | "
            f"{result.outcome} | {result.reason}"
        )


if __name__ == "__main__":
    main()
