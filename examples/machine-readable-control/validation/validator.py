import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml


PASS = "PASS"
FAIL = "FAIL"
APPROVED_EXCEPTION = "APPROVED_EXCEPTION"
NOT_APPLICABLE = "NOT_APPLICABLE"

SCOPE_FIELD_MAP = {
    "privileged_accounts": "privileged",
    "remote_access": "remote_access",
    "sensitive_or_regulated_systems": "sensitive_or_regulated_system_access",
}


@dataclass(frozen=True)
class ValidationResult:
    account_id: str
    username: str
    outcome: str
    reason: str


def load_control(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as control_file:
        return yaml.safe_load(control_file)


def load_environment(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as environment_file:
        return json.load(environment_file)


def _scope_fields(control: dict[str, Any]) -> tuple[str, ...]:
    scope_names = control["control"]["requirement"]["scope"]
    try:
        return tuple(SCOPE_FIELD_MAP[scope_name] for scope_name in scope_names)
    except KeyError as error:
        raise ValueError(f"Unsupported control scope: {error.args[0]}") from error


def _result(account: dict[str, Any], outcome: str, reason: str) -> ValidationResult:
    return ValidationResult(
        account_id=account["account_id"],
        username=account["username"],
        outcome=outcome,
        reason=reason,
    )


def _exception_failure(exception: dict[str, Any], evaluation_date: date) -> str | None:
    if exception.get("status") != "approved":
        return "The exception status is not approved."
    if exception.get("risk_review_completed") is not True:
        return "The exception does not include a completed risk review."
    if exception.get("security_approval") is not True:
        return "The exception does not include security approval."
    if exception.get("governance_approval") is not True:
        return "The exception does not include governance approval."

    try:
        expiration_date = date.fromisoformat(exception["expiration_date"])
    except (KeyError, TypeError, ValueError):
        return "The exception does not include a valid expiration date."

    if expiration_date < evaluation_date:
        return f"The exception expired on {expiration_date.isoformat()}."

    return None


def evaluate_account(
    account: dict[str, Any],
    control: dict[str, Any],
    evaluation_date: date,
) -> ValidationResult:
    applicable_fields = [
        field for field in _scope_fields(control) if account.get(field) is True
    ]

    if not applicable_fields:
        return _result(
            account,
            NOT_APPLICABLE,
            "The account does not meet any scope condition defined by the control.",
        )

    if account.get("mfa_enabled") is True:
        return _result(
            account,
            PASS,
            "The account is in scope and multifactor authentication is enabled.",
        )

    exception = account.get("exception")
    if not isinstance(exception, dict):
        return _result(
            account,
            FAIL,
            "The account is in scope, multifactor authentication is disabled, and no exception exists.",
        )

    exception_failure = _exception_failure(exception, evaluation_date)
    if exception_failure:
        return _result(
            account,
            FAIL,
            f"The account is in scope and multifactor authentication is disabled. {exception_failure}",
        )

    return _result(
        account,
        APPROVED_EXCEPTION,
        "The account is in scope and multifactor authentication is disabled, but its exception is approved, fully reviewed, and unexpired.",
    )


def evaluate_environment(
    control: dict[str, Any],
    environment: dict[str, Any],
    evaluation_date: date,
) -> list[ValidationResult]:
    return [
        evaluate_account(account, control, evaluation_date)
        for account in environment["accounts"]
    ]
