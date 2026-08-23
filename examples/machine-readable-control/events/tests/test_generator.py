import json
import subprocess
import unittest
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from assurance.decision import AssuranceDecision
from events.generator import event_from_decision, generate_events, write_events


EXAMPLE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = EXAMPLE_ROOT.parents[1]


def decision(
    *,
    transition,
    governance_outcome,
    integrity_status="VERIFIED",
    assurance_action,
    subject_id="USR-002",
    reason="Existing assurance decision reason.",
):
    return AssuranceDecision(
        control_id="ACP-001-03",
        subject_id=subject_id,
        governance_outcome=governance_outcome,
        integrity_status=integrity_status,
        assurance_action=assurance_action,
        previous_governance_outcome=None,
        transition=transition,
        reason=reason,
        evaluation_date="2026-08-22",
    )


class EventMappingTests(unittest.TestCase):
    def assert_event_type(self, expected, **decision_fields):
        event = event_from_decision(decision(**decision_fields))
        self.assertIsNotNone(event)
        self.assertEqual(expected, event.event_type)

    def test_new_control_failure_opens_failure_event(self):
        self.assert_event_type(
            "CONTROL_FAILURE_OPENED",
            transition="NEW_CONTROL_FAILURE",
            governance_outcome="FAIL",
            assurance_action="ESCALATE",
        )

    def test_persistent_failure_continues_failure_event(self):
        self.assert_event_type(
            "CONTROL_FAILURE_CONTINUES",
            transition="PERSISTENT_CONTROL_FAILURE",
            governance_outcome="FAIL",
            assurance_action="ESCALATE",
        )

    def test_control_recovery_records_recovery_event(self):
        self.assert_event_type(
            "CONTROL_RECOVERY_RECORDED",
            transition="CONTROL_RECOVERY",
            governance_outcome="PASS",
            assurance_action="RECORD",
        )

    def test_exception_to_failure_escalates_lapse(self):
        self.assert_event_type(
            "EXCEPTION_LAPSE_ESCALATION",
            transition="EXCEPTION_TO_FAILURE",
            governance_outcome="FAIL",
            assurance_action="ESCALATE",
        )

    def test_new_approved_exception_opens_review(self):
        self.assert_event_type(
            "EXCEPTION_REVIEW_OPENED",
            transition="NEW_APPROVED_EXCEPTION",
            governance_outcome="APPROVED_EXCEPTION",
            assurance_action="REVIEW",
        )

    def test_mismatch_and_halt_trust_creates_integrity_incident(self):
        self.assert_event_type(
            "INTEGRITY_INCIDENT",
            transition=None,
            governance_outcome="PASS",
            integrity_status="MISMATCH",
            assurance_action="HALT_TRUST",
        )

    def test_integrity_incident_overrides_transition_mapping(self):
        event = event_from_decision(
            decision(
                transition="NEW_CONTROL_FAILURE",
                governance_outcome="FAIL",
                integrity_status="MISMATCH",
                assurance_action="HALT_TRUST",
            )
        )

        self.assertEqual("INTEGRITY_INCIDENT", event.event_type)


class NoEventTests(unittest.TestCase):
    def assert_no_event(self, transition, outcome, action):
        self.assertIsNone(
            event_from_decision(
                decision(
                    transition=transition,
                    governance_outcome=outcome,
                    assurance_action=action,
                )
            )
        )

    def test_stable_pass_produces_no_event(self):
        self.assert_no_event("STABLE_PASS", "PASS", "RECORD")

    def test_stable_approved_exception_produces_no_event(self):
        self.assert_no_event(
            "STABLE_APPROVED_EXCEPTION", "APPROVED_EXCEPTION", "REVIEW"
        )

    def test_stable_not_applicable_produces_no_event(self):
        self.assert_no_event("STABLE_NOT_APPLICABLE", "NOT_APPLICABLE", "RECORD")

    def test_unavailable_previous_state_produces_no_event(self):
        self.assert_no_event(None, "FAIL", "ESCALATE")


class EventSchemaTests(unittest.TestCase):
    def mapped_events(self):
        inputs = [
            ("NEW_CONTROL_FAILURE", "FAIL", "ESCALATE"),
            ("PERSISTENT_CONTROL_FAILURE", "FAIL", "ESCALATE"),
            ("CONTROL_RECOVERY", "PASS", "RECORD"),
            ("EXCEPTION_TO_FAILURE", "FAIL", "ESCALATE"),
            ("NEW_APPROVED_EXCEPTION", "APPROVED_EXCEPTION", "REVIEW"),
        ]
        return [
            event_from_decision(
                decision(
                    transition=transition,
                    governance_outcome=outcome,
                    assurance_action=action,
                )
            )
            for transition, outcome, action in inputs
        ]

    def test_event_id_is_deterministic(self):
        source = decision(
            transition="NEW_CONTROL_FAILURE",
            governance_outcome="FAIL",
            assurance_action="ESCALATE",
        )

        first = event_from_decision(source)
        second = event_from_decision(source)

        self.assertEqual(first.event_id, second.event_id)
        self.assertEqual(
            "ACP-001-03-USR-002-CONTROL_FAILURE_OPENED-20260822",
            first.event_id,
        )

    def test_severity_mapping_is_exact(self):
        events = self.mapped_events()
        integrity = event_from_decision(
            decision(
                transition="NEW_CONTROL_FAILURE",
                governance_outcome="FAIL",
                integrity_status="MISMATCH",
                assurance_action="HALT_TRUST",
            )
        )

        self.assertEqual(
            ["high", "medium", "info", "medium", "medium", "high"],
            [item.severity for item in [*events, integrity]],
        )

    def test_human_review_flags_are_exact(self):
        events = self.mapped_events()
        integrity = event_from_decision(
            decision(
                transition=None,
                governance_outcome="PASS",
                integrity_status="MISMATCH",
                assurance_action="HALT_TRUST",
            )
        )

        self.assertEqual(
            [True, True, False, True, True, True],
            [item.requires_human_review for item in [*events, integrity]],
        )

    def test_event_consumes_existing_decision_fields_and_serializes(self):
        source = decision(
            transition="CONTROL_RECOVERY",
            governance_outcome="PASS",
            assurance_action="RECORD",
            subject_id="SUBJECT-FROM-DECISION",
            reason="Reason supplied by the approved decision engine.",
        )

        event = event_from_decision(source)
        parsed = json.loads(json.dumps(asdict(event)))

        self.assertEqual("SUBJECT-FROM-DECISION", parsed["subject_id"])
        self.assertEqual("PASS", parsed["governance_outcome"])
        self.assertEqual("VERIFIED", parsed["integrity_status"])
        self.assertEqual("RECORD", parsed["assurance_action"])
        self.assertEqual("CONTROL_RECOVERY", parsed["transition"])
        self.assertEqual(source.reason, parsed["reason"])

    def test_runtime_event_files_are_parseable_and_ignored(self):
        events = generate_events(
            [
                decision(
                    transition="NEW_CONTROL_FAILURE",
                    governance_outcome="FAIL",
                    assurance_action="ESCALATE",
                )
            ]
        )
        with TemporaryDirectory() as temporary_directory:
            paths = write_events(events, Path(temporary_directory))
            parsed = json.loads(paths[0].read_text(encoding="utf-8"))

        self.assertEqual("CONTROL_FAILURE_OPENED", parsed["event_type"])
        runtime_path = (
            EXAMPLE_ROOT
            / "generated-assurance"
            / "events"
            / "sample-event.json"
        )
        completed = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={REPOSITORY_ROOT.as_posix()}",
                "-C",
                str(REPOSITORY_ROOT),
                "check-ignore",
                "--quiet",
                str(runtime_path),
            ],
            check=False,
        )
        self.assertEqual(0, completed.returncode)

    def test_empty_current_event_set_removes_prior_runtime_events(self):
        prior_events = generate_events(
            [
                decision(
                    transition="NEW_CONTROL_FAILURE",
                    governance_outcome="FAIL",
                    assurance_action="ESCALATE",
                )
            ]
        )
        with TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory) / "events"
            write_events(prior_events, output_directory)

            paths = write_events([], output_directory)

            self.assertEqual([], paths)
            self.assertEqual([], list(output_directory.glob("*.json")))


if __name__ == "__main__":
    unittest.main()
