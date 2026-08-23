import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from automation.cli import (
    INTEGRITY_HALT,
    VERIFIED_RUN,
    classify_pipeline_status,
    main,
)


def pipeline_result(*, succeeded, integrity_status, assurance_action):
    return SimpleNamespace(
        succeeded=succeeded,
        integrity_results=[SimpleNamespace(status=integrity_status)],
        decisions=[SimpleNamespace(assurance_action=assurance_action)],
        summary="Synthetic summary.\n",
    )


class PipelineStatusTests(unittest.TestCase):
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
                patch("sys.argv", ["automation"]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}, clear=False),
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
                patch("sys.argv", ["automation"]),
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}, clear=False),
                patch("automation.cli.run_pipeline", return_value=result),
                redirect_stdout(StringIO()),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                main()

            self.assertEqual(
                "assurance_status=integrity_halt\n",
                output.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
