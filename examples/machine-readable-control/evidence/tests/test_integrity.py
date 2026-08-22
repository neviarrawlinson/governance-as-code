import hashlib
import json
import subprocess
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from evidence.generator import generate_evidence_records, write_evidence_records
from evidence.integrity import (
    MISMATCH,
    VERIFIED,
    build_source_integrity,
    get_repository_commit,
    sha256_file,
    verify_evidence,
    write_detached_checksum,
)
from validation.validator import evaluate_environment, load_control, load_environment


EXAMPLE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = EXAMPLE_ROOT.parents[1]
CONTROL_PATH = EXAMPLE_ROOT / "controls" / "ACP-001-03.yaml"
ENVIRONMENT_PATH = EXAMPLE_ROOT / "sample-data" / "identity-environment.json"
VALIDATOR_PATH = EXAMPLE_ROOT / "validation" / "validator.py"
EVALUATION_DATE = date(2026, 8, 22)
GENERATED_AT = datetime(2026, 8, 22, 14, 0, tzinfo=timezone.utc)


class IntegrityTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.control_path = self.directory / "control.yaml"
        self.environment_path = self.directory / "environment.json"
        self.validator_path = self.directory / "validator.py"
        self.control_path.write_bytes(b"control: exact bytes\n")
        self.environment_path.write_bytes(b'{"environment": "exact bytes"}\n')
        self.validator_path.write_bytes(b"def validate():\n    return True\n")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def source_integrity(self):
        return build_source_integrity(
            self.control_path, self.environment_path, self.validator_path
        )

    def write_record(self, outcome="PASS", exception=None):
        record = {
            "metadata": {"evidence_id": "ACP-001-03-USR-TEST-20260822"},
            "result": {"outcome": outcome, "reason": "Validator supplied reason."},
            "integrity": self.source_integrity(),
        }
        if exception is not None:
            record["exception"] = exception
        evidence_path = write_evidence_records([record], self.directory / "evidence")[0]
        return evidence_path, evidence_path.with_suffix(".json.sha256")


class SourceHashTests(IntegrityTestCase):
    def test_control_sha256_matches_exact_file_bytes(self):
        integrity = self.source_integrity()

        self.assertEqual(
            hashlib.sha256(self.control_path.read_bytes()).hexdigest(),
            integrity["control_sha256"],
        )

    def test_environment_sha256_matches_exact_file_bytes(self):
        integrity = self.source_integrity()

        self.assertEqual(
            hashlib.sha256(self.environment_path.read_bytes()).hexdigest(),
            integrity["environment_sha256"],
        )

    def test_validator_sha256_matches_exact_file_bytes(self):
        integrity = self.source_integrity()

        self.assertEqual(
            hashlib.sha256(self.validator_path.read_bytes()).hexdigest(),
            integrity["validator_sha256"],
        )

    def test_detached_checksum_matches_complete_evidence_file(self):
        evidence_path, checksum_path = self.write_record()

        checksum = checksum_path.read_text(encoding="utf-8").split()[0]
        self.assertEqual(sha256_file(evidence_path), checksum)


class IntegrityVerificationTests(IntegrityTestCase):
    def test_unmodified_evidence_and_sources_verify(self):
        evidence_path, checksum_path = self.write_record()

        verification = verify_evidence(
            evidence_path,
            checksum_path,
            self.control_path,
            self.environment_path,
            self.validator_path,
        )

        self.assertEqual(VERIFIED, verification.status)
        self.assertEqual([], verification.mismatched_components)

    def test_modified_evidence_json_mismatches(self):
        evidence_path, checksum_path = self.write_record()
        evidence_path.write_text(
            evidence_path.read_text(encoding="utf-8") + " ", encoding="utf-8"
        )

        verification = verify_evidence(
            evidence_path,
            checksum_path,
            self.control_path,
            self.environment_path,
            self.validator_path,
        )

        self.assertEqual(MISMATCH, verification.status)
        self.assertEqual(MISMATCH, verification.components["evidence_artifact"])

    def test_modified_control_definition_mismatches(self):
        evidence_path, checksum_path = self.write_record()
        self.control_path.write_bytes(b"modified control\n")

        verification = verify_evidence(
            evidence_path,
            checksum_path,
            self.control_path,
            self.environment_path,
            self.validator_path,
        )

        self.assertEqual(MISMATCH, verification.components["control_definition"])

    def test_modified_environment_input_mismatches(self):
        evidence_path, checksum_path = self.write_record()
        self.environment_path.write_bytes(b"modified environment\n")

        verification = verify_evidence(
            evidence_path,
            checksum_path,
            self.control_path,
            self.environment_path,
            self.validator_path,
        )

        self.assertEqual(MISMATCH, verification.components["environment_data"])

    def test_modified_validator_source_mismatches(self):
        evidence_path, checksum_path = self.write_record()
        self.validator_path.write_bytes(b"modified validator\n")

        verification = verify_evidence(
            evidence_path,
            checksum_path,
            self.control_path,
            self.environment_path,
            self.validator_path,
        )

        self.assertEqual(MISMATCH, verification.components["validator_implementation"])

    def test_verifier_identifies_each_mismatched_component(self):
        evidence_path, checksum_path = self.write_record()
        self.environment_path.write_bytes(b"modified environment\n")
        self.validator_path.write_bytes(b"modified validator\n")

        verification = verify_evidence(
            evidence_path,
            checksum_path,
            self.control_path,
            self.environment_path,
            self.validator_path,
        )

        self.assertEqual(
            ["environment_data", "validator_implementation"],
            verification.mismatched_components,
        )

    def test_integrity_verification_does_not_change_governance_outcome(self):
        evidence_path, checksum_path = self.write_record(outcome="PASS")
        before = evidence_path.read_bytes()

        verification = verify_evidence(
            evidence_path,
            checksum_path,
            self.control_path,
            self.environment_path,
            self.validator_path,
        )

        self.assertEqual(VERIFIED, verification.status)
        self.assertEqual(before, evidence_path.read_bytes())
        with evidence_path.open(encoding="utf-8") as evidence_file:
            self.assertEqual("PASS", json.load(evidence_file)["result"]["outcome"])

    def test_malformed_evidence_json_produces_mismatch(self):
        evidence_path, checksum_path = self.write_record()
        evidence_path.write_text("{", encoding="utf-8")

        verification = verify_evidence(
            evidence_path,
            checksum_path,
            self.control_path,
            self.environment_path,
            self.validator_path,
        )

        self.assertEqual(MISMATCH, verification.status)
        self.assertIn("evidence_structure", verification.mismatched_components)

    def test_checksum_naming_another_artifact_produces_mismatch(self):
        evidence_path, checksum_path = self.write_record()
        checksum_path.write_text(
            f"{sha256_file(evidence_path)}  other.json\n", encoding="utf-8"
        )

        verification = verify_evidence(
            evidence_path,
            checksum_path,
            self.control_path,
            self.environment_path,
            self.validator_path,
        )

        self.assertEqual(MISMATCH, verification.components["evidence_artifact"])

    def test_invalid_integrity_algorithm_produces_mismatch(self):
        evidence_path, checksum_path = self.write_record()
        with evidence_path.open(encoding="utf-8") as evidence_file:
            evidence = json.load(evidence_file)
        evidence["integrity"]["algorithm"] = "MD5"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        write_detached_checksum(evidence_path)

        verification = verify_evidence(
            evidence_path,
            checksum_path,
            self.control_path,
            self.environment_path,
            self.validator_path,
        )

        self.assertEqual(MISMATCH, verification.components["integrity_metadata"])

    def test_missing_control_source_produces_component_mismatch(self):
        evidence_path, checksum_path = self.write_record()
        self.control_path.unlink()

        verification = verify_evidence(
            evidence_path,
            checksum_path,
            self.control_path,
            self.environment_path,
            self.validator_path,
        )

        self.assertEqual(MISMATCH, verification.components["control_definition"])


class ExistingEvidenceIntegrationTests(unittest.TestCase):
    def records(self):
        control = load_control(CONTROL_PATH)
        environment = load_environment(ENVIRONMENT_PATH)
        validation_results = evaluate_environment(control, environment, EVALUATION_DATE)
        integrity = build_source_integrity(
            CONTROL_PATH, ENVIRONMENT_PATH, VALIDATOR_PATH
        )
        return generate_evidence_records(
            control,
            environment,
            validation_results,
            EVALUATION_DATE,
            GENERATED_AT,
            integrity,
            get_repository_commit(REPOSITORY_ROOT),
        )

    def test_approved_exception_traceability_remains_intact(self):
        records = self.records()

        self.assertEqual("EXC-001", records[3]["exception"]["exception_id"])
        self.assertTrue(records[3]["exception"]["valid_at_evaluation_time"])

    def test_expired_exception_traceability_remains_intact(self):
        records = self.records()

        self.assertEqual("EXC-002", records[4]["exception"]["exception_id"])
        self.assertFalse(records[4]["exception"]["valid_at_evaluation_time"])

    def test_runtime_evidence_and_checksums_are_ignored_by_git(self):
        paths = [
            EXAMPLE_ROOT / "generated-evidence" / "record.json",
            EXAMPLE_ROOT / "generated-evidence" / "record.json.sha256",
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

    def test_git_provenance_is_captured_when_available(self):
        records = self.records()
        expected_commit = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={REPOSITORY_ROOT.as_posix()}",
                "-C",
                str(REPOSITORY_ROOT),
                "rev-parse",
                "HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        self.assertEqual(expected_commit, records[0]["provenance"]["repository_commit"])

    def test_git_provenance_is_optional_when_unavailable(self):
        with TemporaryDirectory() as temporary_directory:
            self.assertIsNone(get_repository_commit(Path(temporary_directory)))

    def test_verifier_cli_rejects_empty_evidence_directory(self):
        with TemporaryDirectory() as temporary_directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "evidence.verify_cli",
                    "--evidence-directory",
                    temporary_directory,
                ],
                cwd=EXAMPLE_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(1, completed.returncode)
        self.assertIn("MISMATCH", completed.stdout)


if __name__ == "__main__":
    unittest.main()
