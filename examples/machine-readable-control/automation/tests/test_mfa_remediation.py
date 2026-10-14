import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from automation.pipeline import run_pipeline
from integrations.github.issues import Issue, plan_event_operations

class CorrelatedFailureIssue:
    def find_open_issue(self, marker):
        return Issue(3, "Synthetic failure", "") if "ACP-001-03:USR-004" in marker else None
    def has_event_marker(self, issue, marker):
        return False

class MfaRemediationTests(unittest.TestCase):
    def test_current_dataset_recovers_usr_004_without_changing_other_outcomes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous = root / "prior.json"
            subjects = [{"subject_id": sid, "governance_outcome": outcome} for sid, outcome in [("USR-001", "PASS"), ("USR-002", "PASS"), ("USR-003", "PASS"), ("SVC-001", "APPROVED_EXCEPTION"), ("USR-004", "FAIL")]]
            previous.write_text(json.dumps({"control_id": "ACP-001-03", "evaluation_date": "2026-10-14", "subjects": subjects}))
            result = run_pipeline(date(2026, 10, 14), root / "evaluated", previous_state_path=previous)
            self.assertTrue(result.succeeded)
            self.assertEqual(["PASS", "PASS", "PASS", "APPROVED_EXCEPTION", "PASS"], [d.governance_outcome for d in result.decisions])
            recovered = next(d for d in result.decisions if d.subject_id == "USR-004")
            self.assertEqual((recovered.integrity_status, recovered.transition), ("VERIFIED", "CONTROL_RECOVERY"))
            self.assertEqual(1, len(result.events))
            operations = plan_event_operations(result.events[0], CorrelatedFailureIssue())
            self.assertEqual(["COMMENT_ISSUE", "CLOSE_ISSUE"], [o.operation for o in operations])
            self.assertTrue(all(o.issue_number == 3 for o in operations))
