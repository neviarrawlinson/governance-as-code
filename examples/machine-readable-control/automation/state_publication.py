import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile


VERIFIED_RUN = "verified"


@dataclass(frozen=True)
class StatePublicationDecision:
    advance: bool
    reason: str


def governance_events_present(events_directory: Path) -> bool:
    return events_directory.exists() and any(events_directory.glob("*.json"))


def publish_candidate_state(
    candidate_state_path: Path,
    publication_directory: Path,
    decision: StatePublicationDecision,
) -> Path | None:
    if not decision.advance:
        return None
    publication_directory.mkdir(parents=True, exist_ok=True)
    published_path = publication_directory / "trusted-assurance-state.json"
    copyfile(candidate_state_path, published_path)
    return published_path


def decide_state_publication(
    *,
    assurance_status: str,
    event_name: str,
    live_requested: bool,
    live_job_result: str,
    governance_events_present: bool,
) -> StatePublicationDecision:
    if assurance_status != VERIFIED_RUN:
        return StatePublicationDecision(
            False, "Only a VERIFIED assurance run may advance trusted state."
        )

    authorized_live_run = event_name == "workflow_dispatch" and live_requested
    if authorized_live_run:
        if live_job_result == "success":
            return StatePublicationDecision(
                True,
                "Authorized live governance processing completed successfully.",
            )
        return StatePublicationDecision(
            False,
            "Authorized live governance processing did not complete successfully.",
        )

    if governance_events_present:
        return StatePublicationDecision(
            False,
            "Dry-run governance events remain pending authorized live processing.",
        )

    return StatePublicationDecision(
        True, "The VERIFIED dry-run produced no governance events."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Publish a candidate trusted state at an approved lifecycle boundary."
        )
    )
    parser.add_argument("--assurance-status", required=True)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--live-requested", required=True)
    parser.add_argument("--live-job-result", required=True)
    parser.add_argument("--events-directory", type=Path, required=True)
    parser.add_argument("--candidate-state", type=Path, required=True)
    parser.add_argument("--publication-directory", type=Path, required=True)
    return parser.parse_args()


def _write_state_ready(ready: bool) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"state_ready={str(ready).lower()}\n")


def main() -> None:
    args = parse_args()
    decision = decide_state_publication(
        assurance_status=args.assurance_status,
        event_name=args.event_name,
        live_requested=args.live_requested == "true",
        live_job_result=args.live_job_result,
        governance_events_present=governance_events_present(
            args.events_directory
        ),
    )
    published = publish_candidate_state(
        args.candidate_state,
        args.publication_directory,
        decision,
    )
    _write_state_ready(published is not None)
    print(decision.reason)


if __name__ == "__main__":
    main()
