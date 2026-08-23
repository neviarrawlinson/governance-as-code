import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from events.generator import GovernanceEvent
from integrations.github.client import GitHubIssueGateway
from integrations.github.issues import IssueGateway, IssueOperation, process_events


EXAMPLE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVENTS_DIRECTORY = EXAMPLE_ROOT / "generated-assurance" / "events"
DEFAULT_OUTPUT_PATH = (
    EXAMPLE_ROOT / "generated-assurance" / "github-issue-operations.json"
)


def load_events(events_directory: Path) -> list[GovernanceEvent]:
    if not events_directory.exists():
        return []
    return [
        GovernanceEvent(**json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(events_directory.glob("*.json"))
    ]


def render_summary(operations: list[IssueOperation]) -> str:
    lines = ["## GitHub Issues Dry-Run Plan", ""]
    if not operations:
        lines.append("No GitHub Issue operations proposed for this run.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "| Operation | Category | Control | Subject | Issue | Correlation | Reason |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in operations:
        _, _, control_id, subject_id = item.correlation_id.split(":", 3)
        issue = str(item.issue_number) if item.issue_number is not None else "New"
        reason = item.reason.replace("|", "\\|")
        lines.append(
            f"| {item.operation} | {item.workflow_category} | {control_id} | "
            f"{subject_id} | {issue} | `{item.correlation_id}` | {reason} |"
        )
    return "\n".join(lines) + "\n"


def run_integration(
    events_directory: Path,
    output_path: Path,
    gateway: IssueGateway,
    *,
    dry_run: bool,
    summary_path: Path | None = None,
) -> list[IssueOperation]:
    operations = process_events(load_events(events_directory), gateway, dry_run=dry_run)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([asdict(item) for item in operations], indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    summary = render_summary(operations)
    print(summary, end="")
    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(summary)
    return operations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan GitHub Issue operations from structured governance events."
    )
    parser.add_argument("--events-directory", type=Path, default=DEFAULT_EVENTS_DIRECTORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--repository", default=os.environ.get("GITHUB_REPOSITORY")
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Plan issue operations without modifying GitHub (always enabled in Phase 7B).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.repository:
        raise SystemExit("--repository or GITHUB_REPOSITORY is required")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN or GITHUB_TOKEN is required for read-only lookup")
    gateway = GitHubIssueGateway(args.repository, token)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    run_integration(
        args.events_directory,
        args.output,
        gateway,
        dry_run=True,
        summary_path=Path(summary_path) if summary_path else None,
    )


if __name__ == "__main__":
    main()
