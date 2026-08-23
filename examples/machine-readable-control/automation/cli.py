import argparse
import os
from datetime import date
from pathlib import Path

from automation.pipeline import DEFAULT_OUTPUT_DIRECTORY, run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the synthetic Governance as Code assurance pipeline."
    )
    parser.add_argument(
        "--evaluation-date",
        type=date.fromisoformat,
        help="Evaluation date in YYYY-MM-DD format; defaults to the current UTC date.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
    )
    parser.add_argument(
        "--previous-state",
        type=Path,
        help="Path to the most recent prior trusted assurance state, when available.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_pipeline(
        args.evaluation_date,
        args.output_directory,
        previous_state_path=args.previous_state,
    )
    print(result.summary, end="")

    github_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if github_summary:
        with Path(github_summary).open("a", encoding="utf-8", newline="\n") as summary_file:
            summary_file.write(result.summary)

    if not result.succeeded:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
