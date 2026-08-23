import json
from datetime import date
from pathlib import Path
from typing import Any

from assurance.decision import AssuranceDecision
from validation.validator import APPROVED_EXCEPTION, FAIL, NOT_APPLICABLE, PASS


ALLOWED_OUTCOMES = {PASS, FAIL, APPROVED_EXCEPTION, NOT_APPLICABLE}
STATE_KEYS = {"control_id", "evaluation_date", "subjects"}
SUBJECT_KEYS = {"subject_id", "governance_outcome"}


def build_trusted_state(
    control_id: str,
    evaluation_date: date,
    decisions: list[AssuranceDecision],
) -> dict[str, Any]:
    return {
        "control_id": control_id,
        "evaluation_date": evaluation_date.isoformat(),
        "subjects": [
            {
                "subject_id": decision.subject_id,
                "governance_outcome": decision.governance_outcome,
            }
            for decision in decisions
        ],
    }


def _validate_state(state: object, expected_control_id: str) -> dict[str, Any]:
    if not isinstance(state, dict) or set(state) != STATE_KEYS:
        raise ValueError("Trusted state has an invalid structure")
    if state["control_id"] != expected_control_id:
        raise ValueError("Trusted state control ID does not match the current control")
    try:
        date.fromisoformat(state["evaluation_date"])
    except (TypeError, ValueError) as error:
        raise ValueError("Trusted state has an invalid evaluation date") from error
    if not isinstance(state["subjects"], list):
        raise ValueError("Trusted state subjects must be a list")

    subject_ids = []
    for subject in state["subjects"]:
        if not isinstance(subject, dict) or set(subject) != SUBJECT_KEYS:
            raise ValueError("Trusted state subject has an invalid structure")
        subject_id = subject["subject_id"]
        if not isinstance(subject_id, str) or not subject_id:
            raise ValueError("Trusted state subject ID must be a nonempty string")
        if subject["governance_outcome"] not in ALLOWED_OUTCOMES:
            raise ValueError("Trusted state has an unsupported governance outcome")
        subject_ids.append(subject_id)
    if len(subject_ids) != len(set(subject_ids)):
        raise ValueError("Duplicate subject ID in trusted state")
    return state


def load_trusted_state(path: Path, expected_control_id: str) -> dict[str, Any]:
    try:
        state = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Unable to load trusted state: {path}") from error
    return _validate_state(state, expected_control_id)


def previous_outcomes(state: dict[str, Any]) -> dict[str, str]:
    return {
        subject["subject_id"]: subject["governance_outcome"]
        for subject in state["subjects"]
    }


def write_trusted_state(state: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path
