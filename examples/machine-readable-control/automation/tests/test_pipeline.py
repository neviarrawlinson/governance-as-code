import json
import subprocess
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from assurance.decision import ESCALATE, HALT_TRUST, RECORD, REVIEW
from evidence.integrity import IntegrityVerification, MISMATCH, VERIFIED
from automation.pipeline import (
    build_assurance_decision,
    complete_pipeline,
    prepare_pipeline,
    run_pipeline,
)


EXAMPLE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = EXAMPLE_ROOT.parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "governance-assurance.yml"
EVALUATION_DATE = date(2026, 8, 22)
GENERATED_AT = datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc)


class PipelineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.output_directory = Path(self.temporary_directory.name) / "run"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def run_example(self):
        return run_pipeline(
            evaluation_date=EVALUATION_DATE,
            output_directory=self.output_directory,
            generated_at=GENERATED_AT,
        )

    def test_full_synthetic_pipeline_executes_successfully(self):
        result = self.run_example()

        self.assertTrue(result.succeeded)
        self.assertEqual(5, len(result.decisions))

    def test_all_subjects_receive_existing_validator_outcomes(self):
        result = self.run_example()

        self.assertEqual(
            ["PASS", "FAIL", "PASS", "APPROVED_EXCEPTION", "FAIL"],
            [decision.governance_outcome for decision in result.decisions],
        )

    def test_evidence_is_generated_from_validator_outcomes(self):
        prepared = prepare_pipeline(
            EVALUATION_DATE, self.output_directory, GENERATED_AT
        )

        self.assertEqual(
            [item.outcome for item in prepared.validation_results],
            [record["result"]["outcome"] for record in prepared.evidence_records],
        )
        self.assertTrue(all(path.exists() for path in prepared.evidence_paths))

    def test_generated_evidence_verifies_successfully(self):
        result = self.run_example()

        self.assertEqual(
            [VERIFIED] * 5,
            [verification.status for verification in result.integrity_results],
        )

    def test_assurance_actions_come_from_existing_decision_engine(self):
        result = self.run_example()

        self.assertEqual(
            [RECORD, ESCALATE, RECORD, REVIEW, ESCALATE],
            [decision.assurance_action for decision in result.decisions],
        )

    def test_not_applicable_verified_is_delegated_to_record_action(self):
        record = {
            "subject": {"account_id": "USR-OUT-OF-SCOPE"},
            "result": {"outcome": "NOT_APPLICABLE"},
        }
        verification = IntegrityVerification(VERIFIED, {}, [])

        decision = build_assurance_decision(
            "ACP-001-03", record, verification, EVALUATION_DATE
        )

        self.assertEqual("NOT_APPLICABLE", decision.governance_outcome)
        self.assertEqual(RECORD, decision.assurance_action)

    def test_verified_fail_does_not_fail_pipeline(self):
        result = self.run_example()

        failures = [
            decision
            for decision in result.decisions
            if decision.governance_outcome == "FAIL"
        ]
        self.assertEqual([ESCALATE, ESCALATE], [item.assurance_action for item in failures])
        self.assertTrue(result.succeeded)

    def test_explicit_evaluation_date_is_honored(self):
        result = self.run_example()

        self.assertEqual(
            ["2026-08-22"] * 5,
            [decision.evaluation_date for decision in result.decisions],
        )

    def test_default_evaluation_date_uses_current_utc_date(self):
        local_time = datetime(
            2026, 8, 22, 18, 30, tzinfo=timezone(timedelta(hours=-7))
        )
        result = run_pipeline(
            output_directory=self.output_directory,
            generated_at=local_time,
        )

        self.assertEqual("2026-08-23", result.evaluation_date)

    def test_runtime_outputs_are_ignored_by_git(self):
        paths = [
            EXAMPLE_ROOT / "generated-assurance" / "evidence" / "record.json",
            EXAMPLE_ROOT / "generated-assurance" / "evidence" / "record.json.sha256",
            EXAMPLE_ROOT / "generated-assurance" / "assurance-decisions.json",
            EXAMPLE_ROOT / "generated-assurance" / "run-summary.md",
        ]

        for path in paths:
            completed = subprocess.run(
                [
                    "git",
                    "-c",
                    f"safe.directory={REPOSITORY_ROOT.as_posix()}",
                    "-C",
                    str(REPOSITORY_ROOT),
                    "check-ignore",
                    "--quiet",
                    str(path),
                ],
                check=False,
            )
            self.assertEqual(0, completed.returncode)

    def test_human_readable_summary_contains_subjects_and_aggregate_counts(self):
        result = self.run_example()

        self.assertIn("# Governance Assurance Run Summary", result.summary)
        self.assertIn("USR-002", result.summary)
        self.assertIn("| None |", result.summary)
        self.assertIn("| FAIL | 2 |", result.summary)
        self.assertIn("| ESCALATE | 2 |", result.summary)
        self.assertIn("| HALT_TRUST | 0 |", result.summary)

    def test_structured_decisions_serialize_and_parse(self):
        result = self.run_example()

        parsed = json.loads(result.decisions_path.read_text(encoding="utf-8"))
        self.assertEqual(5, len(parsed))
        self.assertEqual("USR-001", parsed[0]["subject_id"])
        self.assertEqual("RECORD", parsed[0]["assurance_action"])

    def test_existing_exception_traceability_remains_in_evidence(self):
        prepared = prepare_pipeline(
            EVALUATION_DATE, self.output_directory, GENERATED_AT
        )

        self.assertEqual("EXC-001", prepared.evidence_records[3]["exception"]["exception_id"])
        self.assertTrue(
            prepared.evidence_records[3]["exception"]["valid_at_evaluation_time"]
        )


class IntegrityFailureTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.output_directory = Path(self.temporary_directory.name) / "run"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_integrity_mismatch_halts_trust_and_fails_pipeline(self):
        prepared = prepare_pipeline(
            EVALUATION_DATE, self.output_directory, GENERATED_AT
        )
        prepared.evidence_paths[0].write_text(
            prepared.evidence_paths[0].read_text(encoding="utf-8") + " ",
            encoding="utf-8",
        )

        result = complete_pipeline(prepared)

        self.assertEqual(MISMATCH, result.integrity_results[0].status)
        self.assertEqual(HALT_TRUST, result.decisions[0].assurance_action)
        self.assertFalse(result.succeeded)


class WorkflowConfigurationTests(unittest.TestCase):
    def workflow(self):
        return yaml.load(
            WORKFLOW_PATH.read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )

    def test_workflow_has_required_triggers_and_path_filters(self):
        workflow = self.workflow()
        triggers = workflow["on"]

        self.assertIn("workflow_dispatch", triggers)
        self.assertEqual("0 6 * * 1", triggers["schedule"][0]["cron"])
        self.assertEqual(
            [
                "examples/machine-readable-control/controls/**",
                "examples/machine-readable-control/validation/**",
                "examples/machine-readable-control/evidence/**",
                "examples/machine-readable-control/assurance/**",
                "examples/machine-readable-control/automation/**",
                "examples/machine-readable-control/sample-data/**",
                ".github/workflows/governance-assurance.yml",
            ],
            triggers["push"]["paths"],
        )

    def test_workflow_uses_read_only_permissions_and_bounded_artifact_retention(self):
        workflow = self.workflow()

        self.assertEqual({"contents": "read"}, workflow["permissions"])
        steps = workflow["jobs"]["assurance"]["steps"]
        upload = next(step for step in steps if step.get("uses", "").startswith("actions/upload-artifact@"))
        self.assertEqual("7", upload["with"]["retention-days"])
        self.assertIn("generated-assurance", upload["with"]["path"])


if __name__ == "__main__":
    unittest.main()
