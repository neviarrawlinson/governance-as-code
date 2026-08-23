import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from assurance.decision import (
    ESCALATE,
    HALT_TRUST,
    RECORD,
    REVIEW,
    AssuranceDecision,
    decide_assurance,
)
from evidence.generator import generate_evidence_records, write_evidence_records
from evidence.integrity import (
    IntegrityVerification,
    build_source_integrity,
    build_source_integrity_from_bytes,
    get_repository_commit,
    verify_evidence,
)
from validation.validator import (
    APPROVED_EXCEPTION,
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ValidationResult,
    evaluate_environment,
)


EXAMPLE_ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = EXAMPLE_ROOT.parents[1]
CONTROL_PATH = EXAMPLE_ROOT / "controls" / "ACP-001-03.yaml"
ENVIRONMENT_PATH = EXAMPLE_ROOT / "sample-data" / "identity-environment.json"
VALIDATOR_PATH = EXAMPLE_ROOT / "validation" / "validator.py"
DEFAULT_OUTPUT_DIRECTORY = EXAMPLE_ROOT / "generated-assurance"

GOVERNANCE_OUTCOMES = (PASS, FAIL, APPROVED_EXCEPTION, NOT_APPLICABLE)
ASSURANCE_ACTIONS = (RECORD, REVIEW, ESCALATE, HALT_TRUST)


@dataclass(frozen=True)
class PreparedPipelineRun:
    control: dict[str, Any]
    environment: dict[str, Any]
    evaluation_date: date
    validation_results: list[ValidationResult]
    evidence_records: list[dict[str, Any]]
    evidence_paths: list[Path]
    output_directory: Path


@dataclass(frozen=True)
class PipelineRun:
    evaluation_date: str
    decisions: list[AssuranceDecision]
    integrity_results: list[IntegrityVerification]
    evidence_paths: list[Path]
    decisions_path: Path
    summary_path: Path
    summary: str
    succeeded: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _evaluation_date(explicit_date: date | None, generated_at: datetime) -> date:
    if explicit_date is not None:
        return explicit_date
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must include timezone information")
    return generated_at.astimezone(timezone.utc).date()


def prepare_pipeline(
    evaluation_date: date,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    generated_at: datetime | None = None,
) -> PreparedPipelineRun:
    generated_at = generated_at or _utc_now()
    control_bytes = CONTROL_PATH.read_bytes()
    environment_bytes = ENVIRONMENT_PATH.read_bytes()
    validator_bytes = VALIDATOR_PATH.read_bytes()
    integrity = build_source_integrity_from_bytes(
        control_bytes, environment_bytes, validator_bytes
    )
    control = yaml.safe_load(control_bytes)
    environment = json.loads(environment_bytes)
    validation_results = evaluate_environment(control, environment, evaluation_date)

    if integrity != build_source_integrity(
        CONTROL_PATH, ENVIRONMENT_PATH, VALIDATOR_PATH
    ):
        raise RuntimeError("Referenced source files changed during pipeline preparation")

    evidence_records = generate_evidence_records(
        control,
        environment,
        validation_results,
        evaluation_date,
        generated_at,
        integrity,
        get_repository_commit(REPOSITORY_ROOT),
    )
    evidence_directory = output_directory / "evidence"
    evidence_paths = write_evidence_records(evidence_records, evidence_directory)
    return PreparedPipelineRun(
        control=control,
        environment=environment,
        evaluation_date=evaluation_date,
        validation_results=validation_results,
        evidence_records=evidence_records,
        evidence_paths=evidence_paths,
        output_directory=output_directory,
    )


def _summary(
    control_id: str,
    evaluation_date: date,
    decisions: list[AssuranceDecision],
) -> str:
    governance_counts = Counter(item.governance_outcome for item in decisions)
    action_counts = Counter(item.assurance_action for item in decisions)
    lines = [
        "# Governance Assurance Run Summary",
        "",
        f"- Control ID: `{control_id}`",
        f"- Evaluation date: `{evaluation_date.isoformat()}`",
        "",
        "| Subject | Governance outcome | Integrity status | Assurance action | Transition | Reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in decisions:
        transition = item.transition or "None"
        lines.append(
            f"| {item.subject_id} | {item.governance_outcome} | "
            f"{item.integrity_status} | {item.assurance_action} | "
            f"{transition} | {item.reason} |"
        )
    lines.extend(
        [
            "",
            "## Aggregate Counts",
            "",
            "| Classification | Count |",
            "| --- | ---: |",
        ]
    )
    for outcome in GOVERNANCE_OUTCOMES:
        lines.append(f"| {outcome} | {governance_counts[outcome]} |")
    for action in ASSURANCE_ACTIONS:
        lines.append(f"| {action} | {action_counts[action]} |")
    return "\n".join(lines) + "\n"


def build_assurance_decision(
    control_id: str,
    evidence_record: dict[str, Any],
    integrity_result: IntegrityVerification,
    evaluation_date: date,
) -> AssuranceDecision:
    """Delegate existing evidence and integrity results to the decision engine."""
    return decide_assurance(
        control_id=control_id,
        subject_id=evidence_record["subject"]["account_id"],
        governance_outcome=evidence_record["result"]["outcome"],
        integrity_status=integrity_result.status,
        evaluation_date=evaluation_date,
    )


def complete_pipeline(prepared: PreparedPipelineRun) -> PipelineRun:
    integrity_results = []
    decisions = []
    control_id = prepared.control["control"]["id"]

    for record, evidence_path in zip(
        prepared.evidence_records, prepared.evidence_paths, strict=True
    ):
        verification = verify_evidence(
            evidence_path,
            evidence_path.with_suffix(".json.sha256"),
            CONTROL_PATH,
            ENVIRONMENT_PATH,
            VALIDATOR_PATH,
        )
        integrity_results.append(verification)
        decisions.append(
            build_assurance_decision(
                control_id, record, verification, prepared.evaluation_date
            )
        )

    summary = _summary(control_id, prepared.evaluation_date, decisions)
    prepared.output_directory.mkdir(parents=True, exist_ok=True)
    decisions_path = prepared.output_directory / "assurance-decisions.json"
    decisions_path.write_text(
        json.dumps([asdict(item) for item in decisions], indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    summary_path = prepared.output_directory / "run-summary.md"
    summary_path.write_text(summary, encoding="utf-8", newline="\n")

    return PipelineRun(
        evaluation_date=prepared.evaluation_date.isoformat(),
        decisions=decisions,
        integrity_results=integrity_results,
        evidence_paths=prepared.evidence_paths,
        decisions_path=decisions_path,
        summary_path=summary_path,
        summary=summary,
        succeeded=all(item.assurance_action != HALT_TRUST for item in decisions),
    )


def run_pipeline(
    evaluation_date: date | None = None,
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY,
    generated_at: datetime | None = None,
) -> PipelineRun:
    generated_at = generated_at or _utc_now()
    resolved_date = _evaluation_date(evaluation_date, generated_at)
    prepared = prepare_pipeline(resolved_date, output_directory, generated_at)
    return complete_pipeline(prepared)
