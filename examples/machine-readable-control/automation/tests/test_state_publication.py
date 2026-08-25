import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from automation.state_publication import (
    StatePublicationDecision,
    decide_state_publication,
    governance_events_present,
    publish_candidate_state,
)


class TrustedStatePublicationPolicyTests(unittest.TestCase):
    def test_dry_run_with_events_does_not_advance_trusted_state(self):
        decision = decide_state_publication(
            assurance_status="verified",
            event_name="push",
            live_requested=False,
            live_job_result="skipped",
            governance_events_present=True,
        )

        self.assertFalse(decision.advance)

    def test_dry_run_without_events_can_advance_trusted_state(self):
        decision = decide_state_publication(
            assurance_status="verified",
            event_name="schedule",
            live_requested=False,
            live_job_result="skipped",
            governance_events_present=False,
        )

        self.assertTrue(decision.advance)

    def test_authorized_live_success_advances_trusted_state_after_processing(self):
        decision = decide_state_publication(
            assurance_status="verified",
            event_name="workflow_dispatch",
            live_requested=True,
            live_job_result="success",
            governance_events_present=True,
        )

        self.assertTrue(decision.advance)

    def test_authorized_live_failure_does_not_advance_trusted_state(self):
        decision = decide_state_publication(
            assurance_status="verified",
            event_name="workflow_dispatch",
            live_requested=True,
            live_job_result="failure",
            governance_events_present=True,
        )

        self.assertFalse(decision.advance)

    def test_integrity_halt_never_advances_trusted_state(self):
        decision = decide_state_publication(
            assurance_status="integrity_halt",
            event_name="workflow_dispatch",
            live_requested=True,
            live_job_result="success",
            governance_events_present=True,
        )

        self.assertFalse(decision.advance)


class CandidateStatePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.candidate = self.directory / "candidate" / "trusted-assurance-state.json"
        self.publication_directory = self.directory / "published"
        self.candidate.parent.mkdir()
        self.state = {
            "control_id": "ACP-001-03",
            "evaluation_date": "2026-08-23",
            "subjects": [
                {"subject_id": "USR-002", "governance_outcome": "PASS"},
                {"subject_id": "USR-004", "governance_outcome": "FAIL"},
            ],
        }
        self.candidate.write_text(json.dumps(self.state), encoding="utf-8")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_approved_candidate_is_copied_to_publication_directory(self):
        published = publish_candidate_state(
            self.candidate,
            self.publication_directory,
            StatePublicationDecision(True, "Authorized live processing succeeded."),
        )

        self.assertEqual(
            self.publication_directory / "trusted-assurance-state.json", published
        )
        self.assertEqual(self.state, json.loads(published.read_text(encoding="utf-8")))

    def test_withheld_candidate_creates_no_authoritative_state_file(self):
        published = publish_candidate_state(
            self.candidate,
            self.publication_directory,
            StatePublicationDecision(False, "Governance events remain pending."),
        )

        self.assertIsNone(published)
        self.assertFalse(self.publication_directory.exists())

    def test_event_detection_uses_structured_event_files(self):
        events_directory = self.directory / "events"
        events_directory.mkdir()

        self.assertFalse(governance_events_present(events_directory))

        (events_directory / "ACP-001-03-USR-002.json").write_text(
            "{}", encoding="utf-8"
        )
        self.assertTrue(governance_events_present(events_directory))


class StatePublicationCliTests(unittest.TestCase):
    def run_cli(self, *, event_name, live_requested, live_job_result, with_event):
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            candidate = directory / "candidate" / "trusted-assurance-state.json"
            events = directory / "events"
            published = directory / "published"
            github_output = directory / "github-output.txt"
            candidate.parent.mkdir()
            events.mkdir()
            candidate.write_text('{"control_id": "ACP-001-03"}', encoding="utf-8")
            if with_event:
                (events / "recovery.json").write_text("{}", encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "automation.state_publication",
                    "--assurance-status",
                    "verified",
                    "--event-name",
                    event_name,
                    "--live-requested",
                    live_requested,
                    "--live-job-result",
                    live_job_result,
                    "--events-directory",
                    str(events),
                    "--candidate-state",
                    str(candidate),
                    "--publication-directory",
                    str(published),
                ],
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "GITHUB_OUTPUT": str(github_output)},
            )
            output = github_output.read_text(encoding="utf-8")
            state_exists = (published / "trusted-assurance-state.json").exists()
            return completed, output, state_exists

    def test_dry_run_cli_withholds_candidate_when_event_is_pending(self):
        completed, output, state_exists = self.run_cli(
            event_name="push",
            live_requested="false",
            live_job_result="skipped",
            with_event=True,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("state_ready=false", output)
        self.assertFalse(state_exists)

    def test_authorized_live_cli_publishes_candidate_after_success(self):
        completed, output, state_exists = self.run_cli(
            event_name="workflow_dispatch",
            live_requested="true",
            live_job_result="success",
            with_event=True,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("state_ready=true", output)
        self.assertTrue(state_exists)


if __name__ == "__main__":
    unittest.main()
