import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from automation.cli import (
    HISTORY_UNRESOLVED,
    INTEGRITY_HALT,
    VERIFIED_RUN,
    classify_pipeline_status,
    main,
)
from automation.pipeline import DEFAULT_OUTPUT_DIRECTORY


def pipeline_result(*, succeeded, integrity_status, assurance_action):
    return SimpleNamespace(
        succeeded=succeeded,
        integrity_results=[SimpleNamespace(status=integrity_status)],
        decisions=[SimpleNamespace(assurance_action=assurance_action)],
        summary="Synthetic summary.\n",
        trusted_state_path=None,
    )


class PipelineStatusTests(unittest.TestCase):
    def healthy_resolution(self):
        return SimpleNamespace(
            historical_comparison_allowed=True,
            issue_operations_allowed=True,
            publication_allowed=True,
            recovery_required=False,
            status="FOUND",
            reason="Found.",
        )

    def test_unresolved_trusted_history_has_distinct_terminal_status(self):
        result = pipeline_result(
            succeeded=True,
            integrity_status="VERIFIED",
            assurance_action="RECORD",
        )

        self.assertEqual(
            HISTORY_UNRESOLVED,
            classify_pipeline_status(result, trusted_history_resolved=False),
        )
    def test_verified_run_has_authenticated_terminal_status(self):
        result = pipeline_result(
            succeeded=True,
            integrity_status="VERIFIED",
            assurance_action="RECORD",
        )

        self.assertEqual(VERIFIED_RUN, classify_pipeline_status(result))

    def test_mismatch_halt_has_authenticated_integrity_status(self):
        result = pipeline_result(
            succeeded=False,
            integrity_status="MISMATCH",
            assurance_action="HALT_TRUST",
        )

        self.assertEqual(INTEGRITY_HALT, classify_pipeline_status(result))

    def test_unexpected_failed_state_is_not_authenticated(self):
        result = pipeline_result(
            succeeded=False,
            integrity_status="VERIFIED",
            assurance_action="ESCALATE",
        )

        with self.assertRaisesRegex(RuntimeError, "Unexpected pipeline terminal state"):
            classify_pipeline_status(result)

    def test_cli_writes_verified_status_to_github_output(self):
        result = pipeline_result(
            succeeded=True,
            integrity_status="VERIFIED",
            assurance_action="RECORD",
        )
        with TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "github-output.txt"
            with (
                patch("sys.argv", ["automation", "--state-resolution", "resolution.json", "--previous-state", "prior.json"]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}, clear=False),
                patch("automation.cli.load_state_resolution", return_value=self.healthy_resolution()),
                patch("automation.cli.run_pipeline", return_value=result),
                redirect_stdout(StringIO()),
            ):
                main()

            self.assertEqual(
                "assurance_status=verified\n",
                output.read_text(encoding="utf-8"),
            )

    def test_cli_writes_integrity_halt_before_nonzero_exit(self):
        result = pipeline_result(
            succeeded=False,
            integrity_status="MISMATCH",
            assurance_action="HALT_TRUST",
        )
        with TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "github-output.txt"
            with (
                patch("sys.argv", ["automation", "--state-resolution", "resolution.json", "--previous-state", "prior.json"]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}, clear=False),
                patch("automation.cli.load_state_resolution", return_value=self.healthy_resolution()),
                patch("automation.cli.run_pipeline", return_value=result),
                redirect_stdout(StringIO()),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                main()

            self.assertEqual(
                "assurance_status=integrity_halt\n",
                output.read_text(encoding="utf-8"),
            )

    def test_unresolved_history_runs_point_in_time_and_preserves_nonzero_exit(self):
        result = pipeline_result(
            succeeded=True,
            integrity_status="VERIFIED",
            assurance_action="RECORD",
        )
        resolution = SimpleNamespace(
            historical_comparison_allowed=False,
            issue_operations_allowed=False,
            publication_allowed=False,
            recovery_required=True,
            status="ABSENT",
            reason="Established history is absent.",
        )
        with TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "github-output.txt"
            with (
                patch("sys.argv", ["automation", "--state-resolution", "resolution.json"]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}, clear=False),
                patch("automation.cli.load_state_resolution", return_value=resolution),
                patch("automation.cli.run_pipeline", return_value=result) as run,
                patch("automation.cli.write_assurance_observation"),
                redirect_stdout(StringIO()),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                main()

            run.assert_called_once_with(
                None,
                DEFAULT_OUTPUT_DIRECTORY,
                previous_state_path=None,
                historical_comparison_allowed=False,
                candidate_state_allowed=False,
            )
            self.assertIn(
                "assurance_status=history_unresolved",
                output.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
