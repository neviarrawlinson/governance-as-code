"""Descriptive, non-authoritative assurance lifecycle diagnostics."""

import argparse
import json
import os
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUTCOMES = ("PASS", "FAIL", "APPROVED_EXCEPTION", "NOT_APPLICABLE")
INTEGRITY = ("VERIFIED", "MISMATCH")
ACTIONS = ("RECORD", "REVIEW", "ESCALATE", "HALT_TRUST")


def _counts(values, order=None):
    counts = Counter(values)
    return {key: counts[key] for key in (order or sorted(counts))}


def _utc(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must include timezone information")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_lifecycle_diagnostic(
    *, run, prior_state, assurance_observation, events, proposed_operations,
    executed_operations, workflow_integration, publication,
    workflow_conclusion, generated_at, trusted_history=None,
):
    """Aggregate existing facts without calculating lifecycle decisions."""
    decisions = assurance_observation.get("decisions", [])
    integrity = assurance_observation.get("integrity_results", [])
    evaluation = {
        "status": assurance_observation.get("status", "NOT_REACHED"),
        "evaluation_date": assurance_observation.get("evaluation_date"),
        "candidate_state_evaluation_date": assurance_observation.get(
            "candidate_state_evaluation_date"
        ),
        "control_id": decisions[0].get("control_id") if decisions else None,
        "subject_count": len(decisions),
        "missing_prior_subject_ids": sorted(
            assurance_observation.get("missing_prior_subject_ids", [])
        ),
        "governance_outcomes": _counts(
            [item["governance_outcome"] for item in decisions], OUTCOMES
        ),
        "integrity_statuses": _counts(
            [item["status"] for item in integrity], INTEGRITY
        ),
        "assurance_actions": _counts(
            [item["assurance_action"] for item in decisions], ACTIONS
        ),
        "transitions": _counts(
            [item["transition"] for item in decisions if item.get("transition")]
        ),
    }
    integration = dict(workflow_integration)
    integration.update({
        "proposed_operation_count": len(proposed_operations),
        "proposed_operation_types": _counts(
            [item["operation"] for item in proposed_operations]
        ),
        "executed_operation_count": len(executed_operations),
        "executed_operation_types": _counts(
            [item["operation"] for item in executed_operations]
        ),
    })
    by_subject = {item["subject_id"]: item for item in decisions}
    halts = [{
        "subject_id": item["subject_id"],
        "mismatched_components": sorted(item.get("mismatched_components", [])),
        "assurance_action": by_subject.get(item["subject_id"], {}).get(
            "assurance_action"
        ),
    } for item in integrity if item.get("status") == "MISMATCH"]
    return {
        "schema_version": "1.0",
        "generated_at": _utc(generated_at),
        "run": dict(run),
        "prior_state": dict(prior_state),
        "trusted_history": dict(trusted_history or {
            "lineage_status": "NOT_REACHED",
            "status": "NOT_REACHED",
            "historical_comparison_allowed": False,
            "issue_operations_allowed": False,
            "publication_allowed": False,
            "recovery_required": False,
            "reason": "Trusted-history resolution metadata is unavailable.",
        }),
        "evaluation": evaluation,
        "events": {
            "status": "GENERATED" if evaluation["status"] == "COMPLETED" else "NOT_REACHED",
            "count": len(events),
            "types": _counts([item["event_type"] for item in events]),
        },
        "workflow_integration": integration,
        "publication": dict(publication),
        "result": {
            "assurance_status": assurance_observation.get("assurance_status"),
            "workflow_conclusion": workflow_conclusion,
            "failed_stage": assurance_observation.get("failure_stage"),
            "failure_reason": assurance_observation.get("failure_reason"),
            "integrity_halt": bool(halts),
            "integrity_halt_details": halts,
        },
    }


def write_diagnostic(diagnostic, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(diagnostic, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return path


def _escape(value):
    return str(value if value is not None else "None").replace(
        "\r", " "
    ).replace("\n", " ").replace("|", "\\|")


def _table(title, counts):
    lines = [f"## {title}", "", "| Classification | Count |", "| --- | ---: |"]
    lines += [f"| {_escape(key)} | {value} |" for key, value in counts.items()]
    return lines + ([] if counts else ["| None | 0 |"])


def render_lifecycle_summary(data):
    run, prior, evaluation = data["run"], data["prior_state"], data["evaluation"]
    history = data["trusted_history"]
    integration, publication, result = (
        data["workflow_integration"], data["publication"], data["result"]
    )
    lines = [
        "# Governance Assurance Lifecycle", "", "## Run", "",
        "| Run | Trigger | Branch | Commit | Assurance status |",
        "| --- | --- | --- | --- | --- |",
        f"| {_escape(run.get('run_number'))} ({_escape(run.get('run_id'))}) | "
        f"{_escape(run.get('trigger'))} | {_escape(run.get('branch'))} | "
        f"{_escape(run.get('commit_sha'))} | {_escape(result.get('assurance_status'))} |",
        "", "## Trusted-State Baseline", "",
        f"- Status: {_escape(prior.get('status'))}",
        f"- Source run: {_escape(prior.get('source_run_id'))}",
        f"- Artifact ID: {_escape(prior.get('artifact_id'))}",
        f"- Prior evaluation date: {_escape(prior.get('evaluation_date'))}",
        f"- Reason: {_escape(prior.get('reason'))}",
        "", "## Trusted-History Resolution", "",
        f"- Lineage status: {_escape(history.get('lineage_status'))}",
        f"- Resolution status: {_escape(history.get('status'))}",
        f"- Historical comparison allowed: {str(bool(history.get('historical_comparison_allowed'))).lower()}",
        f"- Issue operations allowed: {str(bool(history.get('issue_operations_allowed'))).lower()}",
        f"- Publication allowed: {str(bool(history.get('publication_allowed'))).lower()}",
        f"- Recovery required: {str(bool(history.get('recovery_required'))).lower()}",
        f"- Failure stage: {_escape(history.get('failure_stage'))}",
        f"- Resolved source run: {_escape(history.get('source_run_id'))}",
        f"- Resolved artifact ID: {_escape(history.get('artifact_id'))}",
        f"- Resolved evaluation date: {_escape(history.get('prior_evaluation_date'))}",
        f"- Observation mode: {'Historical comparison' if history.get('historical_comparison_allowed') else 'Point-in-time evaluation only'}",
        f"- Reason: {_escape(history.get('reason'))}",
        "", "## Current Evaluation", "",
        f"- Status: {_escape(evaluation.get('status'))}",
        f"- Evaluation date: {_escape(evaluation.get('evaluation_date'))}",
        f"- Subjects evaluated: {evaluation.get('subject_count', 0)}", "",
    ]
    for title, key in (
        ("Governance Outcomes", "governance_outcomes"),
        ("Integrity Status", "integrity_statuses"),
        ("Assurance Actions", "assurance_actions"),
        ("Historical Transitions", "transitions"),
    ):
        lines += _table(title, evaluation[key]) + [""]
    lines += _table("Governance Events", data["events"]["types"]) + [
        "", "## Workflow Operations", "",
        f"- Mode: {_escape(integration.get('mode'))}",
        f"- Live requested: {str(bool(integration.get('live_requested'))).lower()}",
        f"- Live authorized: {str(bool(integration.get('live_authorized'))).lower()}",
        f"- Live job: {_escape(integration.get('live_job_status'))}",
        f"- Proposed operations: {integration.get('proposed_operation_count', 0)}",
        f"- Executed operations: {integration.get('executed_operation_count', 0)}",
        "", "## Trusted-State Publication", "",
        f"- Status: {_escape(publication.get('status'))}",
        f"- Decision: {_escape(publication.get('decision'))}",
        f"- Candidate available: {str(bool(publication.get('candidate_state_available'))).lower()}",
        f"- Candidate promoted: {str(bool(publication.get('candidate_promoted'))).lower()}",
        f"- Upload status: {_escape(publication.get('upload_status'))}",
        f"- Authoritative artifact ID: {_escape(publication.get('authoritative_artifact_id'))}",
        f"- Reason: {_escape(publication.get('reason'))}",
        "", "## Final Result", "",
        f"- Workflow conclusion: {_escape(result.get('workflow_conclusion'))}",
        f"- Assurance status: {_escape(result.get('assurance_status'))}",
        f"- Failed lifecycle stage: {_escape(result.get('failed_stage'))}",
        f"- Failure reason: {_escape(result.get('failure_reason'))}",
        f"- Integrity halt: {str(bool(result.get('integrity_halt'))).lower()}",
    ]
    return "\n".join(lines) + "\n"


def write_assurance_observation(result, status, path):
    def decision_record(decision):
        if is_dataclass(decision):
            return asdict(decision)
        return dict(vars(decision))

    integrity = [{
        "subject_id": getattr(decision, "subject_id", None),
        "status": verification.status,
        "mismatched_components": sorted(
            getattr(verification, "mismatched_components", [])
        ),
    } for decision, verification in zip(
        result.decisions, result.integrity_results, strict=True
    )]
    return write_diagnostic({
        "status": "COMPLETED",
        "evaluation_date": getattr(result, "evaluation_date", None),
        "candidate_state_evaluation_date": (
            getattr(result, "evaluation_date", None)
            if getattr(result, "trusted_state_path", None) is not None
            else None
        ),
        "candidate_state_generated": (
            getattr(result, "trusted_state_path", None) is not None
        ),
        "decisions": [decision_record(item) for item in result.decisions],
        "integrity_results": integrity,
        "missing_prior_subject_ids": sorted(
            getattr(result, "missing_subject_ids", [])
        ),
        "assurance_status": status,
        "failure_stage": (
            "EVIDENCE_INTEGRITY"
            if status == "integrity_halt"
            else "TRUSTED_HISTORY_RESOLUTION"
            if status == "history_unresolved"
            else None
        ),
        "failure_reason": (
            "Evidence integrity returned MISMATCH."
            if status == "integrity_halt"
            else "Authoritative trusted history could not be established."
            if status == "history_unresolved"
            else None
        ),
    }, path)


def write_failure_observation(stage, reason, path):
    return write_diagnostic({
        "status": "NOT_REACHED", "failure_stage": stage, "failure_reason": reason
    }, path)


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def _read_files(path):
    return [_read(item, {}) for item in sorted(path.glob("*.json"))] if path.exists() else []


def _bool(value):
    return value.lower() == "true"


def parse_args():
    parser = argparse.ArgumentParser(description="Render lifecycle diagnostics.")
    parser.add_argument("--runtime-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    required = (
        "repository", "workflow", "run-id", "run-number", "trigger", "branch",
        "commit-sha", "live-requested", "live-authorized", "live-job-status",
        "publication-status", "candidate-state-available", "candidate-promoted",
        "upload-status", "workflow-conclusion",
    )
    for name in required:
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--executed-operations", default="[]")
    parser.add_argument("--publication-decision")
    parser.add_argument("--publication-reason")
    parser.add_argument("--authoritative-artifact-id")
    return parser.parse_args()


def main():
    args = parse_args()
    runtime = args.runtime_directory
    prior = _read(
        runtime / "prior-state-metadata.json",
        {"status": "NOT_REACHED", "reason": "Prior-state metadata is unavailable."},
    )
    observation = _read(
        runtime / "assurance-observation.json",
        {
            "status": "NOT_REACHED",
            "failure_stage": (
                "PRIOR_STATE_RETRIEVAL"
                if prior.get("status") == "UNAVAILABLE"
                else "ASSURANCE_EXECUTION"
            ),
            "failure_reason": prior.get(
                "reason", "Assurance observation is unavailable."
            ),
        },
    )
    trusted_history = _read(
        runtime / "trusted-state-resolution.json",
        {
            "lineage_status": "NOT_REACHED",
            "status": "NOT_REACHED",
            "historical_comparison_allowed": False,
            "issue_operations_allowed": False,
            "publication_allowed": False,
            "recovery_required": False,
            "reason": "Trusted-history resolution metadata is unavailable.",
        },
    )
    try:
        executed = json.loads(args.executed_operations)
    except json.JSONDecodeError:
        executed = []
    diagnostic = build_lifecycle_diagnostic(
        run={
            "repository": args.repository, "workflow": args.workflow,
            "run_id": args.run_id, "run_number": args.run_number,
            "trigger": args.trigger, "branch": args.branch,
            "commit_sha": args.commit_sha,
        },
        prior_state=prior,
        assurance_observation=observation,
        events=_read_files(runtime / "events"),
        proposed_operations=_read(runtime / "github-issue-operations.json", []),
        executed_operations=executed if isinstance(executed, list) else [],
        workflow_integration={
            "mode": "LIVE" if _bool(args.live_requested) else "DRY_RUN",
            "live_requested": _bool(args.live_requested),
            "live_authorized": _bool(args.live_authorized),
            "live_job_status": args.live_job_status.upper(),
        },
        publication={
            "status": args.publication_status.upper(),
            "decision": args.publication_decision,
            "reason": args.publication_reason,
            "candidate_state_available": _bool(args.candidate_state_available),
            "candidate_promoted": _bool(args.candidate_promoted),
            "upload_status": args.upload_status.upper(),
            "authoritative_artifact_id": args.authoritative_artifact_id or None,
        },
        workflow_conclusion=args.workflow_conclusion,
        generated_at=datetime.now(timezone.utc),
        trusted_history=trusted_history,
    )
    args.output_directory.mkdir(parents=True, exist_ok=True)
    write_diagnostic(
        diagnostic, args.output_directory / "lifecycle-diagnostic.json"
    )
    summary = render_lifecycle_summary(diagnostic)
    (args.output_directory / "lifecycle-summary.md").write_text(
        summary, encoding="utf-8", newline="\n"
    )
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open(
            "a", encoding="utf-8", newline="\n"
        ) as stream:
            stream.write(summary)


if __name__ == "__main__":
    main()
