from dataclasses import dataclass
from datetime import date

from evidence.integrity import MISMATCH, VERIFIED
from validation.validator import (
    APPROVED_EXCEPTION,
    FAIL,
    NOT_APPLICABLE,
    PASS,
)


RECORD = "RECORD"
REVIEW = "REVIEW"
ESCALATE = "ESCALATE"
HALT_TRUST = "HALT_TRUST"

GOVERNANCE_OUTCOMES = frozenset(
    {PASS, FAIL, APPROVED_EXCEPTION, NOT_APPLICABLE}
)
INTEGRITY_STATUSES = frozenset({VERIFIED, MISMATCH})

VERIFIED_ACTIONS = {
    PASS: RECORD,
    FAIL: ESCALATE,
    APPROVED_EXCEPTION: REVIEW,
    NOT_APPLICABLE: RECORD,
}

TRANSITIONS = {
    (PASS, FAIL): "NEW_CONTROL_FAILURE",
    (FAIL, FAIL): "PERSISTENT_CONTROL_FAILURE",
    (FAIL, PASS): "CONTROL_RECOVERY",
    (APPROVED_EXCEPTION, FAIL): "EXCEPTION_TO_FAILURE",
    (APPROVED_EXCEPTION, PASS): "EXCEPTION_TO_PASS",
    (PASS, APPROVED_EXCEPTION): "NEW_APPROVED_EXCEPTION",
    (PASS, PASS): "STABLE_PASS",
    (APPROVED_EXCEPTION, APPROVED_EXCEPTION): "STABLE_APPROVED_EXCEPTION",
    (NOT_APPLICABLE, NOT_APPLICABLE): "STABLE_NOT_APPLICABLE",
}

TRANSITION_REASONS = {
    "NEW_CONTROL_FAILURE": "A verified control state changed from PASS to FAIL and requires governance attention.",
    "PERSISTENT_CONTROL_FAILURE": "The verified control failure persists and continues to require governance attention.",
    "CONTROL_RECOVERY": "The verified control state changed from FAIL to PASS.",
    "EXCEPTION_TO_FAILURE": "The verified approved exception no longer protects the control deviation.",
    "EXCEPTION_TO_PASS": "The verified technical state now satisfies the control without relying on the exception.",
    "NEW_APPROVED_EXCEPTION": "The verified control state now relies on a newly approved governance exception.",
    "STABLE_PASS": "The verified control state remains PASS.",
    "STABLE_APPROVED_EXCEPTION": "The verified control state remains covered by an approved exception.",
    "STABLE_NOT_APPLICABLE": "The verified control state remains outside the control scope.",
}

ACTION_REASONS = {
    RECORD: "The verified governance outcome can be recorded without additional action classification.",
    REVIEW: "The verified approved exception requires governance review.",
    ESCALATE: "The verified control failure requires governance attention.",
}


@dataclass(frozen=True)
class AssuranceDecision:
    control_id: str
    subject_id: str
    governance_outcome: str
    integrity_status: str
    assurance_action: str
    previous_governance_outcome: str | None
    transition: str | None
    reason: str
    evaluation_date: str


def _validate_inputs(
    governance_outcome: str,
    integrity_status: str,
    previous_governance_outcome: str | None,
) -> None:
    if governance_outcome not in GOVERNANCE_OUTCOMES:
        raise ValueError(f"Unsupported governance outcome: {governance_outcome}")
    if integrity_status not in INTEGRITY_STATUSES:
        raise ValueError(f"Unsupported integrity status: {integrity_status}")
    if (
        previous_governance_outcome is not None
        and previous_governance_outcome not in GOVERNANCE_OUTCOMES
    ):
        raise ValueError(
            f"Unsupported previous governance outcome: {previous_governance_outcome}"
        )


def _classify_transition(previous: str | None, current: str) -> str | None:
    if previous is None:
        return None
    return TRANSITIONS.get((previous, current), f"{previous}_TO_{current}")


def decide_assurance(
    *,
    control_id: str,
    subject_id: str,
    governance_outcome: str,
    integrity_status: str,
    evaluation_date: date,
    previous_governance_outcome: str | None = None,
) -> AssuranceDecision:
    """Classify an assurance action from existing governance and integrity results."""
    _validate_inputs(
        governance_outcome, integrity_status, previous_governance_outcome
    )
    transition = _classify_transition(
        previous_governance_outcome, governance_outcome
    )

    if integrity_status == MISMATCH:
        action = HALT_TRUST
        reason = (
            "Evidence integrity is MISMATCH, so normal governance interpretation "
            "is halted regardless of the reported outcome or transition."
        )
    else:
        action = VERIFIED_ACTIONS[governance_outcome]
        reason = TRANSITION_REASONS.get(
            transition,
            ACTION_REASONS[action]
            if transition is None
            else (
                f"The verified governance state changed from "
                f"{previous_governance_outcome} to {governance_outcome}; "
                f"the current outcome maps to {action}."
            ),
        )

    return AssuranceDecision(
        control_id=control_id,
        subject_id=subject_id,
        governance_outcome=governance_outcome,
        integrity_status=integrity_status,
        assurance_action=action,
        previous_governance_outcome=previous_governance_outcome,
        transition=transition,
        reason=reason,
        evaluation_date=evaluation_date.isoformat(),
    )
