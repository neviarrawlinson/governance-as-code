import json
import subprocess
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from evidence.generator import (
    build_evidence_record,
    generate_evidence_records,
    write_evidence_records,
)
from validation.validator import (
    APPROVED_EXCEPTION,
    FAIL,
    NOT_APPLICABLE,
    PASS,
    ValidationResult,
    evaluate_environment,
    load_control,
    load_environment,
)


EXAMPLE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = EXAMPLE_ROOT.parents[1]
CONTROL_PATH = EXAMPLE_ROOT / "controls" / "ACP-001-03.yaml"
ENVIRONMENT_PATH = EXAMPLE_ROOT / "sample-data" / "identity-environment.json"
EVALUATION_DATE = date(2026, 8, 22)
GENERATED_AT = datetime(2026, 8, 22, 13, 30, tzinfo=timezone.utc)

CONTROL = {
    "control": {
        "id": "ACP-001-03",
        "title": "Multifactor Authentication",
        "version": "1.0",
        "source": {
            "policy": "Access Control Policy",
            "policy_version": "1.1",
        },
        "validation": {"method": "configuration_validation"},
    }
}


def account(**overrides):
    values = {
        "account_id": "USR-TEST",
        "username": "test.user@example.test",
        "privileged": True,
        "remote_access": False,
        "sensitive_or_regulated_system_access": False,
        "mfa_enabled": True,
        "exception": None,
    }
    values.update(overrides)
    return values


def result(outcome, reason="Governance decision reason.", exception_valid=None):
    return ValidationResult(
        account_id="USR-TEST",
        username="test.user@example.test",
        outcome=outcome,
        reason=reason,
        exception_valid=exception_valid,
    )


class EvidenceRecordTests(unittest.TestCase):
    def test_pass_evidence_contains_validator_result(self):
        record = build_evidence_record(
            CONTROL, account(), result(PASS, "MFA is enabled."), EVALUATION_DATE, GENERATED_AT
        )

        self.assertEqual(PASS, record["result"]["outcome"])
        self.assertEqual("MFA is enabled.", record["result"]["reason"])

    def test_fail_evidence_contains_validator_result(self):
        record = build_evidence_record(
            CONTROL,
            account(mfa_enabled=False),
            result(FAIL, "MFA is disabled."),
            EVALUATION_DATE,
            GENERATED_AT,
        )

        self.assertEqual(FAIL, record["result"]["outcome"])
        self.assertNotIn("exception", record)

    def test_approved_exception_evidence_contains_traceability(self):
        exception = {
            "exception_id": "EXC-001",
            "status": "approved",
            "risk_review_completed": True,
            "security_approval": True,
            "governance_approval": True,
            "expiration_date": "2026-12-31",
        }

        record = build_evidence_record(
            CONTROL,
            account(mfa_enabled=False, exception=exception),
            result(APPROVED_EXCEPTION, exception_valid=True),
            EVALUATION_DATE,
            GENERATED_AT,
        )

        self.assertEqual("EXC-001", record["exception"]["exception_id"])
        self.assertTrue(record["exception"]["risk_review_completed"])
        self.assertTrue(record["exception"]["valid_at_evaluation_time"])

    def test_expired_exception_failure_preserves_traceability(self):
        exception = {
            "exception_id": "EXC-002",
            "status": "approved",
            "risk_review_completed": True,
            "security_approval": True,
            "governance_approval": True,
            "expiration_date": "2026-06-30",
        }

        record = build_evidence_record(
            CONTROL,
            account(mfa_enabled=False, exception=exception),
            result(FAIL, "The exception expired.", exception_valid=False),
            EVALUATION_DATE,
            GENERATED_AT,
        )

        self.assertEqual(FAIL, record["result"]["outcome"])
        self.assertEqual("EXC-002", record["exception"]["exception_id"])
        self.assertFalse(record["exception"]["valid_at_evaluation_time"])

    def test_not_applicable_evidence_can_be_generated(self):
        record = build_evidence_record(
            CONTROL,
            account(privileged=False),
            result(NOT_APPLICABLE),
            EVALUATION_DATE,
            GENERATED_AT,
        )

        self.assertEqual(NOT_APPLICABLE, record["result"]["outcome"])

    def test_evidence_uses_validator_outcome_without_recalculating_it(self):
        record = build_evidence_record(
            CONTROL,
            account(mfa_enabled=False, exception=None),
            result(PASS, "Supplied validator outcome."),
            EVALUATION_DATE,
            GENERATED_AT,
        )

        self.assertEqual(PASS, record["result"]["outcome"])
        self.assertEqual("Supplied validator outcome.", record["result"]["reason"])

    def test_single_record_builder_rejects_mismatched_subject(self):
        mismatched_result = ValidationResult(
            "USR-OTHER", "other@example.test", PASS, "Passed."
        )

        with self.assertRaisesRegex(ValueError, "subject"):
            build_evidence_record(
                CONTROL,
                account(),
                mismatched_result,
                EVALUATION_DATE,
                GENERATED_AT,
            )

    def test_evidence_id_is_deterministic(self):
        record = build_evidence_record(
            CONTROL, account(), result(PASS), EVALUATION_DATE, GENERATED_AT
        )

        self.assertEqual(
            "ACP-001-03-USR-TEST-20260822", record["metadata"]["evidence_id"]
        )

    def test_generated_at_is_utc(self):
        record = build_evidence_record(
            CONTROL, account(), result(PASS), EVALUATION_DATE, GENERATED_AT
        )

        self.assertEqual("2026-08-22T13:30:00Z", record["metadata"]["generated_at"])

    def test_evaluation_date_is_separate_from_generation_time(self):
        record = build_evidence_record(
            CONTROL, account(), result(PASS), EVALUATION_DATE, GENERATED_AT
        )

        self.assertEqual("2026-08-22", record["evaluation"]["evaluation_date"])
        self.assertNotEqual(
            record["evaluation"]["evaluation_date"],
            record["metadata"]["generated_at"],
        )

    def test_control_and_policy_versions_come_from_control_definition(self):
        record = build_evidence_record(
            CONTROL, account(), result(PASS), EVALUATION_DATE, GENERATED_AT
        )

        self.assertEqual("1.0", record["control"]["version"])
        self.assertEqual("1.1", record["control"]["source_policy_version"])

    def test_provenance_paths_are_present(self):
        record = build_evidence_record(
            CONTROL, account(), result(PASS), EVALUATION_DATE, GENERATED_AT
        )

        self.assertEqual(
            {
                "control_definition": "examples/machine-readable-control/controls/ACP-001-03.yaml",
                "environment_data": "examples/machine-readable-control/sample-data/identity-environment.json",
                "validator_implementation": "examples/machine-readable-control/validation/validator.py",
            },
            record["provenance"],
        )

    def test_evidence_serializes_and_parses_as_json(self):
        record = build_evidence_record(
            CONTROL, account(), result(PASS), EVALUATION_DATE, GENERATED_AT
        )

        self.assertEqual(record, json.loads(json.dumps(record)))

    def test_written_evidence_is_ignored_by_git(self):
        generated_path = (
            EXAMPLE_ROOT / "generated-evidence" / "ACP-001-03-USR-TEST-20260822.json"
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
                str(generated_path),
            ],
            check=False,
        )

        self.assertEqual(0, completed.returncode)


class SyntheticEnvironmentEvidenceTests(unittest.TestCase):
    def test_reordered_results_are_matched_to_accounts_by_identity(self):
        environment = {
            "environment": {"data_classification": "synthetic"},
            "accounts": [
                account(account_id="USR-ONE", username="one@example.test"),
                account(account_id="USR-TWO", username="two@example.test"),
            ],
        }
        validation_results = [
            ValidationResult("USR-TWO", "two@example.test", FAIL, "Two failed."),
            ValidationResult("USR-ONE", "one@example.test", PASS, "One passed."),
        ]

        records = generate_evidence_records(
            CONTROL,
            environment,
            validation_results,
            EVALUATION_DATE,
            GENERATED_AT,
        )

        self.assertEqual(
            [("USR-ONE", PASS), ("USR-TWO", FAIL)],
            [
                (record["subject"]["account_id"], record["result"]["outcome"])
                for record in records
            ],
        )

    def test_result_username_must_match_account(self):
        environment = {
            "environment": {"data_classification": "synthetic"},
            "accounts": [account()],
        }
        validation_results = [
            ValidationResult("USR-TEST", "wrong@example.test", PASS, "Passed.")
        ]

        with self.assertRaisesRegex(ValueError, "username"):
            generate_evidence_records(
                CONTROL,
                environment,
                validation_results,
                EVALUATION_DATE,
                GENERATED_AT,
            )

    def test_duplicate_result_account_ids_are_rejected(self):
        environment = {
            "environment": {"data_classification": "synthetic"},
            "accounts": [
                account(account_id="USR-ONE", username="one@example.test"),
                account(account_id="USR-TWO", username="two@example.test"),
            ],
        }
        validation_results = [
            ValidationResult("USR-ONE", "one@example.test", PASS, "Passed."),
            ValidationResult("USR-ONE", "one@example.test", FAIL, "Failed."),
        ]

        with self.assertRaisesRegex(ValueError, "Duplicate validation result"):
            generate_evidence_records(
                CONTROL,
                environment,
                validation_results,
                EVALUATION_DATE,
                GENERATED_AT,
            )

    def test_data_classification_comes_from_environment_metadata(self):
        environment = {
            "environment": {"data_classification": "restricted"},
            "accounts": [account()],
        }

        records = generate_evidence_records(
            CONTROL,
            environment,
            [result(PASS)],
            EVALUATION_DATE,
            GENERATED_AT,
        )

        self.assertEqual("restricted", records[0]["metadata"]["data_classification"])

    def test_generates_one_record_per_existing_account(self):
        control = load_control(CONTROL_PATH)
        environment = load_environment(ENVIRONMENT_PATH)
        validation_results = evaluate_environment(control, environment, EVALUATION_DATE)

        records = generate_evidence_records(
            control,
            environment,
            validation_results,
            EVALUATION_DATE,
            GENERATED_AT,
        )

        self.assertEqual(
            [PASS, FAIL, PASS, APPROVED_EXCEPTION, FAIL],
            [record["result"]["outcome"] for record in records],
        )
        self.assertEqual("EXC-001", records[3]["exception"]["exception_id"])
        self.assertTrue(records[3]["exception"]["valid_at_evaluation_time"])
        self.assertEqual("EXC-002", records[4]["exception"]["exception_id"])
        self.assertFalse(records[4]["exception"]["valid_at_evaluation_time"])

    def test_writes_one_parseable_json_file_per_record(self):
        records = [
            build_evidence_record(
                CONTROL, account(), result(PASS), EVALUATION_DATE, GENERATED_AT
            )
        ]

        with TemporaryDirectory() as temporary_directory:
            paths = write_evidence_records(records, Path(temporary_directory))

            self.assertEqual(1, len(paths))
            with paths[0].open(encoding="utf-8") as evidence_file:
                parsed = json.load(evidence_file)
            self.assertEqual(records[0], parsed)


if __name__ == "__main__":
    unittest.main()
