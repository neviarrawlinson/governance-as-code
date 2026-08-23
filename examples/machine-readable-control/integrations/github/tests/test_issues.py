import unittest

from events.generator import GovernanceEvent
from integrations.github.issues import (
    CLOSE_ISSUE,
    COMMENT_ISSUE,
    CREATE_ISSUE,
    NO_ACTION,
    Issue,
    correlation_id,
    correlation_marker,
    event_marker,
    process_events,
)


def governance_event(
    event_type,
    *,
    subject_id="USR-002",
    outcome="FAIL",
    integrity="VERIFIED",
    action="ESCALATE",
    transition="NEW_CONTROL_FAILURE",
    severity="high",
    review=True,
    reason="Existing event reason from Phase 7A.",
):
    return GovernanceEvent(
        event_id=f"event-{event_type}-{subject_id}",
        event_type=event_type,
        control_id="ACP-001-03",
        subject_id=subject_id,
        evaluation_date="2026-08-22",
        governance_outcome=outcome,
        integrity_status=integrity,
        assurance_action=action,
        transition=transition,
        severity=severity,
        requires_human_review=review,
        reason=reason,
    )


class FakeIssueGateway:
    def __init__(self, issues=None):
        self.issues = list(issues or [])
        self.comments = {}
        self.writes = []

    def find_open_issue(self, marker):
        return next((issue for issue in self.issues if marker in issue.body), None)

    def ensure_labels(self, labels):
        self.writes.append(("ensure_labels", tuple(labels)))

    def create_issue(self, title, body, labels):
        self.writes.append(("create", title, body, tuple(labels)))
        issue = Issue(number=99, title=title, body=body)
        self.issues.append(issue)
        return issue

    def has_event_marker(self, issue, marker):
        if marker in issue.body:
            return True
        return any(marker in body for body in self.comments.get(issue.number, []))

    def comment_issue(self, issue_number, body):
        self.writes.append(("comment", issue_number, body))
        self.comments.setdefault(issue_number, []).append(body)

    def close_issue(self, issue_number):
        self.writes.append(("close", issue_number))


def existing_issue(category, number=42):
    return Issue(
        number=number,
        title="Existing governance workflow",
        body=correlation_marker(
            correlation_id("ACP-001-03", "USR-002", category)
        ),
    )


class ControlFailureWorkflowTests(unittest.TestCase):
    def test_opened_control_failure_creates_issue(self):
        gateway = FakeIssueGateway()

        operations = process_events(
            [governance_event("CONTROL_FAILURE_OPENED")], gateway, dry_run=False
        )

        self.assertEqual([CREATE_ISSUE], [item.operation for item in operations])
        self.assertEqual("create", gateway.writes[-1][0])

    def test_repeated_opened_failure_does_not_duplicate_issue(self):
        gateway = FakeIssueGateway([existing_issue("control-failure")])

        operations = process_events(
            [governance_event("CONTROL_FAILURE_OPENED")], gateway, dry_run=False
        )

        self.assertEqual([NO_ACTION], [item.operation for item in operations])
        self.assertEqual([], gateway.writes)

    def test_persistent_failure_comments_on_existing_issue(self):
        gateway = FakeIssueGateway([existing_issue("control-failure")])
        event = governance_event(
            "CONTROL_FAILURE_CONTINUES",
            transition="PERSISTENT_CONTROL_FAILURE",
            severity="medium",
        )

        operations = process_events([event], gateway, dry_run=False)

        self.assertEqual([COMMENT_ISSUE], [item.operation for item in operations])
        self.assertEqual(("comment", 42), gateway.writes[-1][:2])

    def test_persistent_failure_without_issue_creates_recovered_workflow(self):
        gateway = FakeIssueGateway()
        event = governance_event(
            "CONTROL_FAILURE_CONTINUES",
            transition="PERSISTENT_CONTROL_FAILURE",
            severity="medium",
        )

        operation = process_events([event], gateway, dry_run=True)[0]

        self.assertEqual(CREATE_ISSUE, operation.operation)
        self.assertEqual("RECOVERED_MISSING_OPEN_ISSUE", operation.workflow_condition)
        self.assertIn("persistent verified control failure", operation.body.lower())
        self.assertIn("original CONTROL_FAILURE_OPENED event was not observed", operation.body)

    def test_replayed_persistent_failure_does_not_duplicate_comment(self):
        gateway = FakeIssueGateway([existing_issue("control-failure")])
        event = governance_event(
            "CONTROL_FAILURE_CONTINUES",
            transition="PERSISTENT_CONTROL_FAILURE",
            severity="medium",
        )

        first = process_events([event], gateway, dry_run=False)
        second = process_events([event], gateway, dry_run=False)

        self.assertEqual(COMMENT_ISSUE, first[0].operation)
        self.assertEqual(NO_ACTION, second[0].operation)
        self.assertEqual(1, len(gateway.comments[42]))
        self.assertIn(event_marker(event.event_id), gateway.comments[42][0])

    def test_recovery_comments_then_closes_existing_issue(self):
        gateway = FakeIssueGateway([existing_issue("control-failure")])
        event = governance_event(
            "CONTROL_RECOVERY_RECORDED",
            outcome="PASS",
            action="RECORD",
            transition="CONTROL_RECOVERY",
            severity="info",
            review=False,
        )

        operations = process_events([event], gateway, dry_run=False)

        self.assertEqual(
            [COMMENT_ISSUE, CLOSE_ISSUE],
            [item.operation for item in operations],
        )
        self.assertEqual(["comment", "close"], [item[0] for item in gateway.writes])

    def test_recovery_without_issue_does_not_invent_history(self):
        gateway = FakeIssueGateway()
        event = governance_event(
            "CONTROL_RECOVERY_RECORDED",
            outcome="PASS",
            action="RECORD",
            transition="CONTROL_RECOVERY",
            severity="info",
            review=False,
        )

        operations = process_events([event], gateway, dry_run=False)

        self.assertEqual([NO_ACTION], [item.operation for item in operations])
        self.assertIn("No correlated open issue", operations[0].reason)
        self.assertEqual([], gateway.writes)

    def test_recovery_retry_after_comment_only_closes_issue(self):
        gateway = FakeIssueGateway([existing_issue("control-failure")])
        event = governance_event(
            "CONTROL_RECOVERY_RECORDED",
            outcome="PASS",
            action="RECORD",
            transition="CONTROL_RECOVERY",
            severity="info",
            review=False,
        )
        gateway.comments[42] = [event_marker(event.event_id)]

        operations = process_events([event], gateway, dry_run=False)

        self.assertEqual([CLOSE_ISSUE], [item.operation for item in operations])
        self.assertEqual([("close", 42)], gateway.writes)

    def test_exception_lapse_creates_or_updates_control_failure_workflow(self):
        event = governance_event(
            "EXCEPTION_LAPSE_ESCALATION",
            transition="EXCEPTION_TO_FAILURE",
            severity="medium",
        )
        missing = process_events([event], FakeIssueGateway(), dry_run=True)
        existing = process_events(
            [event],
            FakeIssueGateway([existing_issue("control-failure")]),
            dry_run=True,
        )

        self.assertEqual(CREATE_ISSUE, missing[0].operation)
        self.assertEqual(COMMENT_ISSUE, existing[0].operation)
        self.assertIn("human governance attention", missing[0].body.lower())

    def test_replayed_exception_lapse_does_not_duplicate_comment(self):
        gateway = FakeIssueGateway([existing_issue("control-failure")])
        event = governance_event(
            "EXCEPTION_LAPSE_ESCALATION",
            transition="EXCEPTION_TO_FAILURE",
            severity="medium",
        )

        first = process_events([event], gateway, dry_run=False)
        second = process_events([event], gateway, dry_run=False)

        self.assertEqual(COMMENT_ISSUE, first[0].operation)
        self.assertEqual(NO_ACTION, second[0].operation)
        self.assertEqual(1, len(gateway.comments[42]))


class SeparateWorkflowTests(unittest.TestCase):
    def test_new_exception_review_creates_review_issue(self):
        event = governance_event(
            "EXCEPTION_REVIEW_OPENED",
            outcome="APPROVED_EXCEPTION",
            action="REVIEW",
            transition="NEW_APPROVED_EXCEPTION",
            severity="medium",
        )

        operation = process_events([event], FakeIssueGateway(), dry_run=True)[0]

        self.assertEqual(CREATE_ISSUE, operation.operation)
        self.assertIn("approved exception review", operation.title.lower())
        self.assertEqual(
            ("governance-as-code", "exception-review"), operation.labels
        )

    def test_repeated_exception_review_does_not_duplicate(self):
        event = governance_event(
            "EXCEPTION_REVIEW_OPENED",
            outcome="APPROVED_EXCEPTION",
            action="REVIEW",
            transition="NEW_APPROVED_EXCEPTION",
            severity="medium",
        )
        gateway = FakeIssueGateway([existing_issue("exception-review")])

        operation = process_events([event], gateway, dry_run=False)[0]

        self.assertEqual(NO_ACTION, operation.operation)
        self.assertEqual([], gateway.writes)

    def test_integrity_incident_creates_high_priority_issue(self):
        event = governance_event(
            "INTEGRITY_INCIDENT",
            outcome="PASS",
            integrity="MISMATCH",
            action="HALT_TRUST",
            transition="STABLE_PASS",
        )

        operation = process_events([event], FakeIssueGateway(), dry_run=True)[0]

        self.assertEqual(CREATE_ISSUE, operation.operation)
        self.assertIn("MISMATCH", operation.body)
        self.assertIn("HALT_TRUST", operation.body)
        self.assertIn("should not be relied upon", operation.body)
        self.assertEqual(
            ("governance-as-code", "integrity-incident"), operation.labels
        )

    def test_live_integrity_incident_uses_existing_event_without_bypassing_semantics(self):
        event = governance_event(
            "INTEGRITY_INCIDENT",
            outcome="PASS",
            integrity="MISMATCH",
            action="HALT_TRUST",
            transition="STABLE_PASS",
        )
        gateway = FakeIssueGateway()

        operations = process_events([event], gateway, dry_run=False)

        self.assertEqual([CREATE_ISSUE], [item.operation for item in operations])
        self.assertIn("MISMATCH", operations[0].body)
        self.assertIn("HALT_TRUST", operations[0].body)
        self.assertEqual("create", gateway.writes[-1][0])

    def test_repeated_integrity_incident_does_not_duplicate(self):
        event = governance_event(
            "INTEGRITY_INCIDENT",
            integrity="MISMATCH",
            action="HALT_TRUST",
        )
        gateway = FakeIssueGateway([existing_issue("integrity-incident")])

        operation = process_events([event], gateway, dry_run=False)[0]

        self.assertEqual(NO_ACTION, operation.operation)
        self.assertEqual([], gateway.writes)

    def test_correlation_identifiers_are_deterministic_and_category_specific(self):
        failure = correlation_id("ACP-001-03", "USR-002", "control-failure")
        repeated = correlation_id("ACP-001-03", "USR-002", "control-failure")
        exception = correlation_id("ACP-001-03", "USR-002", "exception-review")
        integrity = correlation_id("ACP-001-03", "USR-002", "integrity-incident")

        self.assertEqual("gac-v1:control-failure:ACP-001-03:USR-002", failure)
        self.assertEqual(failure, repeated)
        self.assertEqual(3, len({failure, exception, integrity}))


class ContentAndExecutionTests(unittest.TestCase):
    def test_issue_body_contains_existing_event_context(self):
        event = governance_event("CONTROL_FAILURE_OPENED")

        operation = process_events([event], FakeIssueGateway(), dry_run=True)[0]

        for expected in (
            "ACP-001-03",
            "USR-002",
            "FAIL",
            "VERIFIED",
            "ESCALATE",
            "NEW_CONTROL_FAILURE",
            "CONTROL_FAILURE_OPENED",
            "high",
            "2026-08-22",
            "Existing event reason from Phase 7A.",
            "Human review required: `true`",
            "synthetic Governance as Code demonstration",
            "gac-v1:control-failure:ACP-001-03:USR-002",
        ):
            self.assertIn(expected, operation.body)

    def test_control_failure_labels_are_bounded(self):
        operation = process_events(
            [governance_event("CONTROL_FAILURE_OPENED")],
            FakeIssueGateway(),
            dry_run=True,
        )[0]

        self.assertEqual(
            ("governance-as-code", "control-failure"), operation.labels
        )

    def test_dry_run_describes_create_without_writes(self):
        gateway = FakeIssueGateway()

        operations = process_events(
            [governance_event("CONTROL_FAILURE_OPENED")], gateway, dry_run=True
        )

        self.assertEqual(CREATE_ISSUE, operations[0].operation)
        self.assertEqual([], gateway.writes)

    def test_dry_run_describes_comment_without_writes(self):
        gateway = FakeIssueGateway([existing_issue("control-failure")])
        event = governance_event(
            "CONTROL_FAILURE_CONTINUES",
            transition="PERSISTENT_CONTROL_FAILURE",
            severity="medium",
        )

        operations = process_events([event], gateway, dry_run=True)

        self.assertEqual(COMMENT_ISSUE, operations[0].operation)
        self.assertEqual([], gateway.writes)

    def test_dry_run_describes_close_without_writes(self):
        gateway = FakeIssueGateway([existing_issue("control-failure")])
        event = governance_event(
            "CONTROL_RECOVERY_RECORDED",
            outcome="PASS",
            action="RECORD",
            transition="CONTROL_RECOVERY",
            severity="info",
            review=False,
        )

        operations = process_events([event], gateway, dry_run=True)

        self.assertEqual(
            [COMMENT_ISSUE, CLOSE_ISSUE],
            [item.operation for item in operations],
        )
        self.assertEqual([], gateway.writes)

    def test_dry_run_does_not_plan_duplicate_creates_for_correlated_events(self):
        gateway = FakeIssueGateway()
        opened = governance_event("CONTROL_FAILURE_OPENED")
        persistent = governance_event(
            "CONTROL_FAILURE_CONTINUES",
            transition="PERSISTENT_CONTROL_FAILURE",
            severity="medium",
        )

        operations = process_events([opened, persistent], gateway, dry_run=True)

        self.assertEqual(
            [CREATE_ISSUE, COMMENT_ISSUE],
            [item.operation for item in operations],
        )
        self.assertEqual(1, sum(item.operation == CREATE_ISSUE for item in operations))
        self.assertEqual([], gateway.writes)

    def test_dry_run_simulates_close_before_correlated_reopen(self):
        gateway = FakeIssueGateway([existing_issue("control-failure")])
        recovery = governance_event(
            "CONTROL_RECOVERY_RECORDED",
            outcome="PASS",
            action="RECORD",
            transition="CONTROL_RECOVERY",
            severity="info",
            review=False,
        )
        reopened = governance_event("CONTROL_FAILURE_OPENED")

        operations = process_events([recovery, reopened], gateway, dry_run=True)

        self.assertEqual(
            [COMMENT_ISSUE, CLOSE_ISSUE, CREATE_ISSUE],
            [item.operation for item in operations],
        )
        self.assertEqual([], gateway.writes)

    def test_empty_event_set_produces_no_operation(self):
        gateway = FakeIssueGateway()

        self.assertEqual([], process_events([], gateway, dry_run=True))
        self.assertEqual([], gateway.writes)

    def test_existing_event_values_are_consumed_without_recalculation(self):
        event = governance_event(
            "CONTROL_FAILURE_OPENED",
            outcome="APPROVED_EXCEPTION",
            integrity="MISMATCH",
            action="RECORD",
            transition="CUSTOM_TRANSITION",
            severity="info",
            review=False,
            reason="Deliberately supplied event values.",
        )

        operation = process_events([event], FakeIssueGateway(), dry_run=True)[0]

        self.assertEqual(CREATE_ISSUE, operation.operation)
        self.assertIn("APPROVED_EXCEPTION", operation.body)
        self.assertIn("MISMATCH", operation.body)
        self.assertIn("RECORD", operation.body)
        self.assertIn("CUSTOM_TRANSITION", operation.body)
        self.assertIn("Severity: `info`", operation.body)
        self.assertIn("Human review required: `false`", operation.body)
        self.assertIn("Deliberately supplied event values.", operation.body)


if __name__ == "__main__":
    unittest.main()
