import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from validation.validator import (
    APPROVED_EXCEPTION,
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ValidationResult,
)


VALIDATOR_ID = "acp-001-03-synthetic-validator-v1"
ALLOWED_OUTCOMES = {PASS, FAIL, APPROVED_EXCEPTION, NOT_APPLICABLE}
PROVENANCE = {
    "control_definition": "examples/machine-readable-control/controls/ACP-001-03.yaml",
    "environment_data": "examples/machine-readable-control/sample-data/identity-environment.json",
    "validator_implementation": "examples/machine-readable-control/validation/validator.py",
}


def _utc_timestamp(generated_at: datetime) -> str:
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must include timezone information")
    return generated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _evidence_id(control_id: str, account_id: str, evaluation_date: date) -> str:
    return f"{control_id}-{account_id}-{evaluation_date:%Y%m%d}"


def build_evidence_record(
    control_definition: dict[str, Any],
    account: dict[str, Any],
    validation_result: ValidationResult,
    evaluation_date: date,
    generated_at: datetime,
    data_classification: str = "synthetic",
) -> dict[str, Any]:
    if (
        validation_result.account_id != account["account_id"]
        or validation_result.username != account["username"]
    ):
        raise ValueError("Validation result subject does not match account")
    if validation_result.outcome not in ALLOWED_OUTCOMES:
        raise ValueError(f"Unsupported governance outcome: {validation_result.outcome}")

    control = control_definition["control"]
    record = {
        "metadata": {
            "evidence_id": _evidence_id(
                control["id"], account["account_id"], evaluation_date
            ),
            "evidence_type": "control_validation",
            "generated_at": _utc_timestamp(generated_at),
            "data_classification": data_classification,
        },
        "control": {
            "id": control["id"],
            "title": control["title"],
            "version": control["version"],
            "source_policy": control["source"]["policy"],
            "source_policy_version": control["source"]["policy_version"],
        },
        "evaluation": {
            "evaluation_date": evaluation_date.isoformat(),
            "validation_method": control["validation"]["method"],
            "validator_id": VALIDATOR_ID,
        },
        "subject": {
            "type": "identity_account",
            "account_id": account["account_id"],
            "username": account["username"],
        },
        "result": {
            "outcome": validation_result.outcome,
            "reason": validation_result.reason,
        },
        "provenance": dict(PROVENANCE),
    }

    exception = account.get("exception")
    if isinstance(exception, dict) and validation_result.exception_valid is not None:
        record["exception"] = {
            "exception_id": exception.get("exception_id"),
            "status": exception.get("status"),
            "risk_review_completed": exception.get("risk_review_completed"),
            "security_approval": exception.get("security_approval"),
            "governance_approval": exception.get("governance_approval"),
            "expiration_date": exception.get("expiration_date"),
            "valid_at_evaluation_time": validation_result.exception_valid,
        }

    return record


def generate_evidence_records(
    control_definition: dict[str, Any],
    environment: dict[str, Any],
    validation_results: list[ValidationResult],
    evaluation_date: date,
    generated_at: datetime,
) -> list[dict[str, Any]]:
    accounts = environment["accounts"]
    account_ids = [account["account_id"] for account in accounts]
    if len(account_ids) != len(set(account_ids)):
        raise ValueError("Duplicate account ID in environment data")

    results_by_account_id = {}
    for validation_result in validation_results:
        if validation_result.account_id in results_by_account_id:
            raise ValueError(
                f"Duplicate validation result for account: {validation_result.account_id}"
            )
        results_by_account_id[validation_result.account_id] = validation_result

    if set(account_ids) != set(results_by_account_id):
        raise ValueError("Environment accounts and validation result subjects do not match")

    data_classification = environment["environment"]["data_classification"]
    records = []
    for account in accounts:
        validation_result = results_by_account_id[account["account_id"]]
        if validation_result.username != account["username"]:
            raise ValueError(
                f"Validation result username does not match account {account['account_id']}"
            )
        records.append(
            build_evidence_record(
                control_definition,
                account,
                validation_result,
                evaluation_date,
                generated_at,
                data_classification,
            )
        )

    return records


def write_evidence_records(
    records: list[dict[str, Any]], output_directory: Path
) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for record in records:
        path = output_directory / f"{record['metadata']['evidence_id']}.json"
        with path.open("w", encoding="utf-8", newline="\n") as evidence_file:
            json.dump(record, evidence_file, indent=2)
            evidence_file.write("\n")
        paths.append(path)
    return paths
