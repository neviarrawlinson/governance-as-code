import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from assurance.decision import decide_assurance
from automation.state import build_trusted_state, load_trusted_state, write_trusted_state


EVALUATION_DATE = date(2026, 8, 22)


class TrustedStateSchemaTests(unittest.TestCase):
    def decisions(self):
        return [
            decide_assurance(
                control_id="ACP-001-03",
                subject_id="USR-001",
                governance_outcome="PASS",
                integrity_status="VERIFIED",
                evaluation_date=EVALUATION_DATE,
            ),
            decide_assurance(
                control_id="ACP-001-03",
                subject_id="USR-002",
                governance_outcome="FAIL",
                integrity_status="VERIFIED",
                evaluation_date=EVALUATION_DATE,
            ),
        ]

    def test_state_contains_only_historical_comparison_fields(self):
        state = build_trusted_state("ACP-001-03", EVALUATION_DATE, self.decisions())

        self.assertEqual(
            {
                "control_id": "ACP-001-03",
                "evaluation_date": "2026-08-22",
                "subjects": [
                    {"subject_id": "USR-001", "governance_outcome": "PASS"},
                    {"subject_id": "USR-002", "governance_outcome": "FAIL"},
                ],
            },
            state,
        )

    def test_state_serializes_and_parses_successfully(self):
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "trusted-assurance-state.json"
            write_trusted_state(
                build_trusted_state("ACP-001-03", EVALUATION_DATE, self.decisions()),
                path,
            )

            loaded = load_trusted_state(path, "ACP-001-03")

        self.assertEqual("2026-08-22", loaded["evaluation_date"])
        self.assertEqual("PASS", loaded["subjects"][0]["governance_outcome"])
        json.dumps(loaded)

    def test_state_rejects_duplicate_subject_ids(self):
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "trusted-assurance-state.json"
            path.write_text(
                json.dumps(
                    {
                        "control_id": "ACP-001-03",
                        "evaluation_date": "2026-08-21",
                        "subjects": [
                            {"subject_id": "USR-001", "governance_outcome": "PASS"},
                            {"subject_id": "USR-001", "governance_outcome": "FAIL"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Duplicate subject"):
                load_trusted_state(path, "ACP-001-03")

    def test_state_rejects_evaluation_date_after_current_evaluation(self):
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "trusted-assurance-state.json"
            path.write_text(
                json.dumps(
                    {
                        "control_id": "ACP-001-03",
                        "evaluation_date": "2026-08-23",
                        "subjects": [
                            {"subject_id": "USR-001", "governance_outcome": "PASS"}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "after the current evaluation"):
                load_trusted_state(
                    path,
                    "ACP-001-03",
                    current_evaluation_date=date(2026, 8, 22),
                )


if __name__ == "__main__":
    unittest.main()
