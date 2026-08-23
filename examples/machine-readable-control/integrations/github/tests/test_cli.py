import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from integrations.github.cli import load_events, parse_args, run_integration

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


if __name__ == "__main__":
    unittest.main()
