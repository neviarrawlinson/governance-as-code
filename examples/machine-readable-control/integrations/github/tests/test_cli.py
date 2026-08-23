import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from integrations.github.cli import (
    live_execution_authorized,
    load_events,
    parse_args,
    run_integration,
)

from test_issues import FakeIssueGateway, governance_event


class GitHubIntegrationCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.events_directory = self.root / "events"
        self.events_directory.mkdir()
        self.output_path = self.root / "github-issue-operations.json"
        self.summary_path = self.root / "summary.md"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_event(self, event):
        self.events_directory.joinpath(f"{event.event_id}.json").write_text(
            json.dumps(event.__dict__), encoding="utf-8"
        )

    def test_loads_real_structured_event_json(self):
        event = governance_event("CONTROL_FAILURE_OPENED")
        self.write_event(event)

        loaded = load_events(self.events_directory)

        self.assertEqual([event], loaded)

    def test_run_writes_parseable_operation_plan_and_summary(self):
        self.write_event(governance_event("CONTROL_FAILURE_OPENED"))

        with redirect_stdout(StringIO()):
            operations = run_integration(
                self.events_directory,
                self.output_path,
                FakeIssueGateway(),
                dry_run=True,
                summary_path=self.summary_path,
            )

        parsed = json.loads(self.output_path.read_text(encoding="utf-8"))
        summary = self.summary_path.read_text(encoding="utf-8")
        self.assertEqual("CREATE_ISSUE", parsed[0]["operation"])
        self.assertEqual(operations[0].correlation_id, parsed[0]["correlation_id"])
        self.assertIn("GitHub Issues Dry-Run Plan", summary)
        self.assertIn("CREATE_ISSUE", summary)
        self.assertIn(operations[0].correlation_id, summary)

    def test_cli_defaults_to_dry_run(self):
        with patch("sys.argv", ["github-integration"]):
            args = parse_args()

        self.assertTrue(args.dry_run)

    def test_cli_requires_explicit_live_flag_to_enable_writes(self):
        with patch("sys.argv", ["github-integration", "--live"]):
            args = parse_args()

        self.assertFalse(args.dry_run)

    def test_explicit_dry_run_flag_remains_read_only(self):
        with patch("sys.argv", ["github-integration", "--dry-run"]):
            args = parse_args()

        self.assertTrue(args.dry_run)

    def test_push_context_cannot_authorize_live_execution(self):
        self.assertFalse(live_execution_authorized("push", "true"))

    def test_schedule_context_cannot_authorize_live_execution(self):
        self.assertFalse(live_execution_authorized("schedule", "true"))

    def test_manual_false_cannot_authorize_live_execution(self):
        self.assertFalse(live_execution_authorized("workflow_dispatch", "false"))

    def test_manual_true_explicitly_authorizes_live_execution(self):
        self.assertTrue(live_execution_authorized("workflow_dispatch", "true"))

    def test_empty_events_write_empty_plan_without_gateway_writes(self):
        gateway = FakeIssueGateway()

        with redirect_stdout(StringIO()):
            operations = run_integration(
                self.events_directory,
                self.output_path,
                gateway,
                dry_run=True,
                summary_path=self.summary_path,
            )

        self.assertEqual([], operations)
        self.assertEqual([], json.loads(self.output_path.read_text(encoding="utf-8")))
        self.assertIn("No GitHub Issue operations proposed", self.summary_path.read_text())
        self.assertEqual([], gateway.writes)

    def test_live_mode_executes_existing_planned_operation(self):
        self.write_event(governance_event("CONTROL_FAILURE_OPENED"))
        gateway = FakeIssueGateway()

        with redirect_stdout(StringIO()):
            operations = run_integration(
                self.events_directory,
                self.output_path,
                gateway,
                dry_run=False,
                summary_path=self.summary_path,
            )

        self.assertEqual("CREATE_ISSUE", operations[0].operation)
        self.assertEqual(["ensure_labels", "create"], [item[0] for item in gateway.writes])
        self.assertIn("GitHub Issues Live Execution", self.summary_path.read_text())


if __name__ == "__main__":
    unittest.main()
