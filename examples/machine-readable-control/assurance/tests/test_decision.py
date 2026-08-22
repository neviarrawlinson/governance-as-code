import json
import unittest
from dataclasses import asdict
from datetime import date

from assurance.decision import (
    ESCALATE,
    HALT_TRUST,
    RECORD,
    REVIEW,
    decide_assurance,
)


EVALUATION_DATE = date(2026, 8, 22)


def decide(governance_outcome, integrity_status, previous=None):
    return decide_assurance(
        control_id="ACP-001-03",
        subject_id="USR-002",
        governance_outcome=governance_outcome,
        integrity_status=integrity_status,
        evaluation_date=EVALUATION_DATE,
        previous_governance_outcome=previous,
    )


class PrimaryDecisionMatrixTests(unittest.TestCase):
    def test_pass_with_verified_integrity_is_recorded(self):
        self.assertEqual(RECORD, decide("PASS", "VERIFIED").assurance_action)

    def test_fail_with_verified_integrity_is_escalated(self):
        self.assertEqual(ESCALATE, decide("FAIL", "VERIFIED").assurance_action)

    def test_approved_exception_with_verified_integrity_is_reviewed(self):
        self.assertEqual(
            REVIEW,
            decide("APPROVED_EXCEPTION", "VERIFIED").assurance_action,
        )

    def test_not_applicable_with_verified_integrity_is_recorded(self):
        self.assertEqual(
            RECORD,
            decide("NOT_APPLICABLE", "VERIFIED").assurance_action,
        )

    def test_pass_with_mismatch_halts_trust(self):
        self.assertEqual(HALT_TRUST, decide("PASS", "MISMATCH").assurance_action)

    def test_fail_with_mismatch_halts_trust(self):
        self.assertEqual(HALT_TRUST, decide("FAIL", "MISMATCH").assurance_action)

    def test_approved_exception_with_mismatch_halts_trust(self):
        self.assertEqual(
            HALT_TRUST,
            decide("APPROVED_EXCEPTION", "MISMATCH").assurance_action,
        )

    def test_not_applicable_with_mismatch_halts_trust(self):
        self.assertEqual(
            HALT_TRUST,
            decide("NOT_APPLICABLE", "MISMATCH").assurance_action,
        )


class TransitionTests(unittest.TestCase):
    def assert_transition(self, previous, current, expected):
        self.assertEqual(
            expected,
            decide(current, "VERIFIED", previous).transition,
        )

    def test_pass_to_fail_is_new_control_failure(self):
        self.assert_transition("PASS", "FAIL", "NEW_CONTROL_FAILURE")

    def test_fail_to_fail_is_persistent_control_failure(self):
        self.assert_transition("FAIL", "FAIL", "PERSISTENT_CONTROL_FAILURE")

    def test_fail_to_pass_is_control_recovery(self):
        self.assert_transition("FAIL", "PASS", "CONTROL_RECOVERY")

    def test_approved_exception_to_fail_is_exception_to_failure(self):
        self.assert_transition(
            "APPROVED_EXCEPTION", "FAIL", "EXCEPTION_TO_FAILURE"
        )

    def test_approved_exception_to_pass_is_exception_to_pass(self):
        self.assert_transition("APPROVED_EXCEPTION", "PASS", "EXCEPTION_TO_PASS")

    def test_pass_to_approved_exception_is_new_approved_exception(self):
        self.assert_transition(
            "PASS", "APPROVED_EXCEPTION", "NEW_APPROVED_EXCEPTION"
        )

    def test_pass_to_pass_is_stable_pass(self):
        self.assert_transition("PASS", "PASS", "STABLE_PASS")

    def test_approved_exception_remains_stable(self):
        self.assert_transition(
            "APPROVED_EXCEPTION",
            "APPROVED_EXCEPTION",
            "STABLE_APPROVED_EXCEPTION",
        )

    def test_not_applicable_remains_stable(self):
        self.assert_transition(
            "NOT_APPLICABLE", "NOT_APPLICABLE", "STABLE_NOT_APPLICABLE"
        )

    def test_unlisted_transition_uses_generic_identifier(self):
        self.assert_transition(
            "NOT_APPLICABLE", "PASS", "NOT_APPLICABLE_TO_PASS"
        )

    def test_integrity_mismatch_overrides_transition_action(self):
        result = decide("FAIL", "MISMATCH", "PASS")

        self.assertEqual("NEW_CONTROL_FAILURE", result.transition)
        self.assertEqual(HALT_TRUST, result.assurance_action)


class StructuredDecisionTests(unittest.TestCase):
    def test_decision_serializes_as_structured_json(self):
        result = decide("FAIL", "VERIFIED", "PASS")

        serialized = json.dumps(asdict(result))
        parsed = json.loads(serialized)

        self.assertEqual("ACP-001-03", parsed["control_id"])
        self.assertEqual("USR-002", parsed["subject_id"])
        self.assertEqual("FAIL", parsed["governance_outcome"])
        self.assertEqual("VERIFIED", parsed["integrity_status"])
        self.assertEqual("ESCALATE", parsed["assurance_action"])
        self.assertEqual("PASS", parsed["previous_governance_outcome"])
        self.assertEqual("NEW_CONTROL_FAILURE", parsed["transition"])
        self.assertTrue(parsed["reason"])
        self.assertEqual("2026-08-22", parsed["evaluation_date"])

    def test_governance_outcome_is_consumed_without_technical_state(self):
        result = decide("FAIL", "VERIFIED")

        self.assertEqual("FAIL", result.governance_outcome)
        self.assertEqual(ESCALATE, result.assurance_action)

    def test_integrity_status_is_consumed_without_source_files(self):
        result = decide("PASS", "MISMATCH")

        self.assertEqual("MISMATCH", result.integrity_status)
        self.assertEqual(HALT_TRUST, result.assurance_action)

    def test_previous_outcome_is_omitted_when_not_provided(self):
        result = decide("PASS", "VERIFIED")

        self.assertIsNone(result.previous_governance_outcome)
        self.assertIsNone(result.transition)

    def test_unknown_governance_outcome_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "governance outcome"):
            decide("UNKNOWN", "VERIFIED")

    def test_unknown_integrity_status_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "integrity status"):
            decide("PASS", "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
