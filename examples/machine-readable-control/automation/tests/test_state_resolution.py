import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from automation.state_resolution import (
    ABSENT,
    ESTABLISHED,
    EXPIRED,
    FOUND,
    INELIGIBLE,
    INVALID,
    NOT_REACHED,
    UNAVAILABLE,
    load_state_resolution,
    resolve_trusted_state,
    write_state_resolution,
)


EXAMPLE_ROOT = Path(__file__).resolve().parents[2]
LINEAGE_PATH = EXAMPLE_ROOT / "automation" / "trusted-state-lineage.json"


class TrustedStateResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.lineage_path = self.directory / "lineage.json"
        self.metadata_path = self.directory / "retrieval.json"
        self.state_path = self.directory / "trusted-assurance-state.json"
        self.lineage_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "control_id": "ACP-001-03",
                    "lineage_id": "ACP-001-03-synthetic-assurance",
                    "lineage_status": "ESTABLISHED",
                    "authoritative_state_previously_established": True,
                    "first_authoritative_run_id": "32799613802",
                    "first_authoritative_artifact_id": "9546047131",
                    "first_evaluation_date": "2026-08-22",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_metadata(self, status, **values):
        data = {"status": status, "reason": values.pop("reason", status)}
        data.update(values)
        self.metadata_path.write_text(json.dumps(data), encoding="utf-8")

    def write_state(self, **changes):
        state = {
            "control_id": "ACP-001-03",
            "evaluation_date": "2026-08-24",
            "subjects": [
                {"subject_id": "USR-002", "governance_outcome": "PASS"},
                {"subject_id": "USR-004", "governance_outcome": "FAIL"},
            ],
        }
        state.update(changes)
        self.state_path.write_text(json.dumps(state), encoding="utf-8")

    def write_found_metadata(self):
        self.write_metadata(
            "FOUND",
            source_run_id="32799613802",
            artifact_id="9546047131",
            artifact_name="trusted-assurance-state",
        )

    def resolve(self):
        return resolve_trusted_state(
            lineage_path=self.lineage_path,
            retrieval_metadata_path=self.metadata_path,
            state_path=self.state_path,
            expected_control_id="ACP-001-03",
            current_evaluation_date=date(2026, 8, 25),
        )

    def test_established_lineage_with_healthy_state_allows_existing_lifecycle(self):
        self.write_state()
        self.write_found_metadata()

        resolution = self.resolve()

        self.assertEqual((ESTABLISHED, FOUND), (resolution.lineage_status, resolution.status))
        self.assertTrue(resolution.historical_comparison_allowed)
        self.assertTrue(resolution.issue_operations_allowed)
        self.assertTrue(resolution.publication_allowed)
        self.assertFalse(resolution.recovery_required)
        self.assertEqual("32799613802", resolution.source_run_id)
        self.assertEqual("2026-08-24", resolution.prior_evaluation_date)

    def test_established_lineage_with_absent_state_fails_closed(self):
        self.write_metadata("ABSENT", reason="No artifact bytes were found.")

        resolution = self.resolve()

        self.assertEqual(ABSENT, resolution.status)
        self.assertFalse(resolution.historical_comparison_allowed)
        self.assertFalse(resolution.issue_operations_allowed)
        self.assertFalse(resolution.publication_allowed)
        self.assertTrue(resolution.recovery_required)

    def test_expired_unavailable_and_ineligible_states_fail_closed(self):
        for status in (EXPIRED, UNAVAILABLE, INELIGIBLE, NOT_REACHED):
            with self.subTest(status=status):
                self.write_metadata(status)
                resolution = self.resolve()
                self.assertEqual(status, resolution.status)
                self.assertTrue(resolution.recovery_required)
                self.assertFalse(resolution.historical_comparison_allowed)

    def test_api_and_download_unavailability_remain_distinguishable(self):
        for failure_stage in ("API_RETRIEVAL", "ARTIFACT_DOWNLOAD"):
            with self.subTest(failure_stage=failure_stage):
                self.write_metadata("UNAVAILABLE", failure_stage=failure_stage)
                self.assertEqual(failure_stage, self.resolve().failure_stage)

    def test_malformed_json_and_schema_are_invalid(self):
        for content in ("not-json", '{"control_id": "ACP-001-03"}'):
            with self.subTest(content=content):
                self.state_path.write_text(content, encoding="utf-8")
                self.write_found_metadata()
                resolution = self.resolve()
                self.assertEqual(INVALID, resolution.status)
                self.assertTrue(resolution.recovery_required)
                self.assertNotIn(str(self.directory), resolution.reason)

    def test_control_mismatch_future_date_unsupported_outcome_and_duplicate_are_invalid(self):
        invalid_states = (
            {"control_id": "OTHER"},
            {"evaluation_date": "not-a-date"},
            {"evaluation_date": "2026-08-26"},
            {"subjects": [{"subject_id": "USR-002", "governance_outcome": "UNKNOWN"}]},
            {"subjects": [
                {"subject_id": "USR-002", "governance_outcome": "PASS"},
                {"subject_id": "USR-002", "governance_outcome": "FAIL"},
            ]},
        )
        for changes in invalid_states:
            with self.subTest(changes=changes):
                self.write_state(**changes)
                self.write_found_metadata()
                self.assertEqual(INVALID, self.resolve().status)

    def test_found_artifact_without_required_source_metadata_is_ineligible(self):
        self.write_state()
        self.write_metadata("FOUND")

        self.assertEqual(INELIGIBLE, self.resolve().status)

    def test_resolution_json_is_deterministic_and_contains_no_state_payload(self):
        self.write_state()
        self.write_metadata("FOUND", source_run_id="32799613802", artifact_id="9546047131")
        resolution = self.resolve()
        first = write_state_resolution(resolution, self.directory / "one.json").read_bytes()
        second = write_state_resolution(resolution, self.directory / "two.json").read_bytes()

        self.assertEqual(first, second)
        payload = json.loads(first)
        self.assertNotIn("subjects", payload)
        self.assertNotIn("governance_outcome", first.decode())

    def test_loaded_resolution_rejects_fail_open_flag_combinations(self):
        self.write_metadata("ABSENT")
        payload = json.loads(
            write_state_resolution(
                self.resolve(), self.directory / "resolution.json"
            ).read_text(encoding="utf-8")
        )
        payload["publication_allowed"] = True
        path = self.directory / "inconsistent-resolution.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "inconsistent"):
            load_state_resolution(path)

    def test_repository_declaration_anchors_the_established_control_lineage(self):
        lineage = json.loads(LINEAGE_PATH.read_text(encoding="utf-8"))

        self.assertEqual("1.0", lineage["schema_version"])
        self.assertEqual("ACP-001-03", lineage["control_id"])
        self.assertEqual("ESTABLISHED", lineage["lineage_status"])
        self.assertTrue(lineage["authoritative_state_previously_established"])
        self.assertEqual("32799613802", lineage["first_authoritative_run_id"])
        self.assertEqual("9546047131", lineage["first_authoritative_artifact_id"])
        self.assertEqual("2026-08-22", lineage["first_evaluation_date"])


if __name__ == "__main__":
    unittest.main()
