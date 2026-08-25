"""Resolve trusted-history availability without inferring governance history."""

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from automation.state import load_trusted_state


ESTABLISHED = "ESTABLISHED"
FOUND = "FOUND"
ABSENT = "ABSENT"
EXPIRED = "EXPIRED"
UNAVAILABLE = "UNAVAILABLE"
INVALID = "INVALID"
INELIGIBLE = "INELIGIBLE"
NOT_REACHED = "NOT_REACHED"

LINEAGE_KEYS = {
    "schema_version",
    "control_id",
    "lineage_id",
    "lineage_status",
    "authoritative_state_previously_established",
    "first_authoritative_run_id",
    "first_authoritative_artifact_id",
    "first_evaluation_date",
}
RAW_STATUSES = {FOUND, ABSENT, EXPIRED, UNAVAILABLE, INELIGIBLE, NOT_REACHED}


@dataclass(frozen=True)
class TrustedStateResolution:
    lineage_id: str
    lineage_status: str
    status: str
    historical_comparison_allowed: bool
    issue_operations_allowed: bool
    publication_allowed: bool
    recovery_required: bool
    reason: str
    failure_stage: str | None = None
    source_run_id: str | None = None
    artifact_id: str | None = None
    artifact_name: str | None = None
    prior_evaluation_date: str | None = None


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Unable to load {label}: {path}") from error


def load_lineage(path: Path, expected_control_id: str) -> dict[str, Any]:
    lineage = _read_json(path, "trusted-state lineage declaration")
    if not isinstance(lineage, dict) or set(lineage) != LINEAGE_KEYS:
        raise ValueError("Trusted-state lineage declaration has an invalid structure")
    if lineage["schema_version"] != "1.0":
        raise ValueError("Trusted-state lineage declaration version is unsupported")
    if lineage["control_id"] != expected_control_id:
        raise ValueError("Trusted-state lineage control ID does not match")
    if lineage["lineage_status"] != ESTABLISHED:
        raise ValueError("Trusted-state lineage status is unsupported in Phase 8C-1")
    if lineage["authoritative_state_previously_established"] is not True:
        raise ValueError("Established lineage must record prior authoritative state")
    for key in (
        "lineage_id",
        "first_authoritative_run_id",
        "first_authoritative_artifact_id",
    ):
        if not isinstance(lineage[key], str) or not lineage[key]:
            raise ValueError(f"Trusted-state lineage {key} must be a nonempty string")
    try:
        date.fromisoformat(lineage["first_evaluation_date"])
    except (TypeError, ValueError) as error:
        raise ValueError("Trusted-state lineage first evaluation date is invalid") from error
    return lineage


def _unsafe_resolution(lineage: dict[str, Any], status: str, reason: str, metadata):
    return TrustedStateResolution(
        lineage_id=lineage["lineage_id"],
        lineage_status=lineage["lineage_status"],
        status=status,
        historical_comparison_allowed=False,
        issue_operations_allowed=False,
        publication_allowed=False,
        recovery_required=True,
        reason=reason,
        failure_stage=metadata.get("failure_stage"),
        source_run_id=metadata.get("source_run_id"),
        artifact_id=metadata.get("artifact_id"),
        artifact_name=metadata.get("artifact_name"),
    )


def resolve_trusted_state(
    *,
    lineage_path: Path,
    retrieval_metadata_path: Path,
    state_path: Path,
    expected_control_id: str,
    current_evaluation_date: date,
) -> TrustedStateResolution:
    lineage = load_lineage(lineage_path, expected_control_id)
    try:
        metadata = _read_json(retrieval_metadata_path, "retrieval metadata")
    except ValueError as error:
        return _unsafe_resolution(lineage, UNAVAILABLE, str(error), {})
    if not isinstance(metadata, dict) or metadata.get("status") not in RAW_STATUSES:
        return _unsafe_resolution(
            lineage, UNAVAILABLE, "Trusted-state retrieval metadata is invalid.", {}
        )
    raw_status = metadata["status"]
    if raw_status != FOUND:
        return _unsafe_resolution(
            lineage,
            raw_status,
            metadata.get("reason") or "Authoritative trusted history was not resolved.",
            metadata,
        )
    required_source = (
        metadata.get("source_run_id"),
        metadata.get("artifact_id"),
        metadata.get("artifact_name"),
    )
    if (
        not all(isinstance(value, str) and value for value in required_source)
        or metadata["artifact_name"] != "trusted-assurance-state"
    ):
        return _unsafe_resolution(
            lineage,
            INELIGIBLE,
            "Retrieved trusted state lacks required eligible source metadata.",
            metadata,
        )
    try:
        state = load_trusted_state(
            state_path,
            expected_control_id,
            current_evaluation_date=current_evaluation_date,
        )
    except ValueError as error:
        bounded_reason = str(error).replace(
            str(state_path), "trusted-assurance-state.json"
        )
        return _unsafe_resolution(lineage, INVALID, bounded_reason, metadata)
    return TrustedStateResolution(
        lineage_id=lineage["lineage_id"],
        lineage_status=lineage["lineage_status"],
        status=FOUND,
        historical_comparison_allowed=True,
        issue_operations_allowed=True,
        publication_allowed=True,
        recovery_required=False,
        reason="Authoritative trusted history was found and validated.",
        failure_stage=None,
        source_run_id=metadata.get("source_run_id"),
        artifact_id=metadata.get("artifact_id"),
        artifact_name=metadata.get("artifact_name"),
        prior_evaluation_date=state["evaluation_date"],
    )


def write_state_resolution(resolution: TrustedStateResolution, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(resolution), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def load_state_resolution(path: Path) -> TrustedStateResolution:
    data = _read_json(path, "trusted-state resolution")
    expected_keys = set(TrustedStateResolution.__dataclass_fields__)
    if not isinstance(data, dict) or set(data) != expected_keys:
        raise ValueError("Trusted-state resolution has an invalid structure")
    if data["status"] not in RAW_STATUSES | {INVALID}:
        raise ValueError("Trusted-state resolution status is unsupported")
    for key in (
        "historical_comparison_allowed",
        "issue_operations_allowed",
        "publication_allowed",
        "recovery_required",
    ):
        if not isinstance(data[key], bool):
            raise ValueError("Trusted-state resolution flags must be boolean")
    if data["lineage_status"] != ESTABLISHED:
        raise ValueError("Trusted-state resolution lineage status is unsupported")
    allowed = (
        data["historical_comparison_allowed"],
        data["issue_operations_allowed"],
        data["publication_allowed"],
    )
    consistent = (
        data["status"] == FOUND
        and allowed == (True, True, True)
        and data["recovery_required"] is False
    ) or (
        data["status"] != FOUND
        and allowed == (False, False, False)
        and data["recovery_required"] is True
    )
    if not consistent:
        raise ValueError("Trusted-state resolution flags are inconsistent")
    return TrustedStateResolution(**data)


def _write_outputs(resolution: TrustedStateResolution) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with Path(output).open("a", encoding="utf-8", newline="\n") as stream:
        for name in (
            "historical_comparison_allowed",
            "issue_operations_allowed",
            "publication_allowed",
            "recovery_required",
        ):
            stream.write(f"{name}={str(getattr(resolution, name)).lower()}\n")
        stream.write(f"resolution_status={resolution.status}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve trusted assurance history.")
    parser.add_argument("--lineage", type=Path, required=True)
    parser.add_argument("--retrieval-metadata", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--control-id", required=True)
    parser.add_argument("--evaluation-date", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    resolution = resolve_trusted_state(
        lineage_path=args.lineage,
        retrieval_metadata_path=args.retrieval_metadata,
        state_path=args.state,
        expected_control_id=args.control_id,
        current_evaluation_date=args.evaluation_date,
    )
    write_state_resolution(resolution, args.output)
    _write_outputs(resolution)
    print(resolution.reason)


if __name__ == "__main__":
    main()
