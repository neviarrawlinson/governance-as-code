import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from assurance.decision import ESCALATE, HALT_TRUST, RECORD, REVIEW, AssuranceDecision
from evidence.integrity import MISMATCH, VERIFIED
from validation.validator import APPROVED_EXCEPTION, FAIL, PASS


CONTROL_FAILURE_OPENED = "CONTROL_FAILURE_OPENED"
CONTROL_FAILURE_CONTINUES = "CONTROL_FAILURE_CONTINUES"
CONTROL_RECOVERY_RECORDED = "CONTROL_RECOVERY_RECORDED"
EXCEPTION_LAPSE_ESCALATION = "EXCEPTION_LAPSE_ESCALATION"
EXCEPTION_REVIEW_OPENED = "EXCEPTION_REVIEW_OPENED"
INTEGRITY_INCIDENT = "INTEGRITY_INCIDENT"

EVENT_MAPPINGS = {
    ("NEW_CONTROL_FAILURE", FAIL, VERIFIED, ESCALATE): CONTROL_FAILURE_OPENED,
    ("PERSISTENT_CONTROL_FAILURE", FAIL, VERIFIED, ESCALATE): CONTROL_FAILURE_CONTINUES,
    ("CONTROL_RECOVERY", PASS, VERIFIED, RECORD): CONTROL_RECOVERY_RECORDED,
    ("EXCEPTION_TO_FAILURE", FAIL, VERIFIED, ESCALATE): EXCEPTION_LAPSE_ESCALATION,
    ("NEW_APPROVED_EXCEPTION", APPROVED_EXCEPTION, VERIFIED, REVIEW): EXCEPTION_REVIEW_OPENED,
}

SEVERITIES = {
    CONTROL_FAILURE_OPENED: "high",
    CONTROL_FAILURE_CONTINUES: "medium",
    CONTROL_RECOVERY_RECORDED: "info",
    EXCEPTION_LAPSE_ESCALATION: "medium",
    EXCEPTION_REVIEW_OPENED: "medium",
    INTEGRITY_INCIDENT: "high",
}

HUMAN_REVIEW = {
    CONTROL_FAILURE_OPENED: True,
    CONTROL_FAILURE_CONTINUES: True,
    CONTROL_RECOVERY_RECORDED: False,
    EXCEPTION_LAPSE_ESCALATION: True,
    EXCEPTION_REVIEW_OPENED: True,
    INTEGRITY_INCIDENT: True,
}


@dataclass(frozen=True)
class GovernanceEvent:
    event_id: str
    event_type: str
    control_id: str
    subject_id: str
    evaluation_date: str
    governance_outcome: str
    integrity_status: str
    assurance_action: str
    transition: str | None
    severity: str
    requires_human_review: bool
    reason: str


def _event_type(decision: AssuranceDecision) -> str | None:
    if (
        decision.integrity_status == MISMATCH
        and decision.assurance_action == HALT_TRUST
    ):
        return INTEGRITY_INCIDENT
    return EVENT_MAPPINGS.get(
        (
            decision.transition,
            decision.governance_outcome,
            decision.integrity_status,
            decision.assurance_action,
        )
    )


def event_from_decision(decision: AssuranceDecision) -> GovernanceEvent | None:
    """Translate an existing assurance decision without recalculating it."""
    event_type = _event_type(decision)
    if event_type is None:
        return None
    compact_date = date.fromisoformat(decision.evaluation_date).strftime("%Y%m%d")
    return GovernanceEvent(
        event_id=(
            f"{decision.control_id}-{decision.subject_id}-"
            f"{event_type}-{compact_date}"
        ),
        event_type=event_type,
        control_id=decision.control_id,
        subject_id=decision.subject_id,
        evaluation_date=decision.evaluation_date,
        governance_outcome=decision.governance_outcome,
        integrity_status=decision.integrity_status,
        assurance_action=decision.assurance_action,
        transition=decision.transition,
        severity=SEVERITIES[event_type],
        requires_human_review=HUMAN_REVIEW[event_type],
        reason=decision.reason,
    )


def generate_events(decisions: list[AssuranceDecision]) -> list[GovernanceEvent]:
    events = (event_from_decision(decision) for decision in decisions)
    return [event for event in events if event is not None]


def write_events(
    events: list[GovernanceEvent], output_directory: Path
) -> list[Path]:
    if output_directory.exists():
        for prior_event_path in output_directory.glob("*.json"):
            prior_event_path.unlink()
    if not events:
        return []
    output_directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for event in events:
        path = output_directory / f"{event.event_id}.json"
        path.write_text(
            json.dumps(asdict(event), indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        paths.append(path)
    return paths
