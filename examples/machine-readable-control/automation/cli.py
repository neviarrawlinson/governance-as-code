import argparse
import os
from datetime import date
from pathlib import Path

from assurance.decision import HALT_TRUST
from automation.pipeline import DEFAULT_OUTPUT_DIRECTORY, PipelineRun, run_pipeline
from evidence.integrity import MISMATCH, VERIFIED


VERIFIED_RUN = "verified"
INTEGRITY_HALT = "integrity_halt"


def classify_pipeline_status(result: PipelineRun) -> str:
    pairs = list(zip(result.integrity_results, result.decisions, strict=True))
    if result.succeeded and all(
        integrity.status == VERIFIED for integrity, _ in pairs
    ):
        return VERIFIED_RUN
    mismatches = [
        (integrity, decision)
        for integrity, decision in pairs
        if integrity.status == MISMATCH
    ]
    if (
        not result.succeeded
        and mismatches
        and all(
            decision.assurance_action == HALT_TRUST
            for _, decision in mismatches
        )
    ):
        return INTEGRITY_HALT
    raise RuntimeError("Unexpected pipeline terminal state")


def _write_pipeline_status(status: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"assurance_status={status}\n")


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
    _write_pipeline_status(classify_pipeline_status(result))
    print(result.summary, end="")

    github_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if github_summary:
        with Path(github_summary).open("a", encoding="utf-8", newline="\n") as summary_file:
            summary_file.write(result.summary)

    if not result.succeeded:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
