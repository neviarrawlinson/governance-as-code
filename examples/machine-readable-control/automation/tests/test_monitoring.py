import hashlib
import json
import unittest
import os
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from automation import monitoring as m

REPO = 'neviarrawlinson/governance-as-code'
NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


def run(identifier=1, *, age=1, conclusion='success', event='schedule', branch='main'):
    return dict(id=identifier, created_at=(NOW - timedelta(days=age)).isoformat(),
                path=m.WORKFLOW, head_branch=branch, event=event, status='completed',
                conclusion=conclusion, head_sha='a' * 40,
                repository={'id': 10, 'full_name': REPO}, head_repository={'id': 10})


class MonitoringTests(unittest.TestCase):
    def assess(self, runs):
        return m.assess(runs, repository=REPO, now=NOW)

    def issue(self, report, state='open'):
        digest = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
        return dict(number=7, state=state, body=(m.MARKER + '\n' + m.START + '\n'
                    + m.render(report) + f'\n<!-- status-sha256:{digest} -->\n' + m.END
                    + '\nHuman review notes: preserve this decision.'))

    def test_fresh_scheduled_success_is_healthy(self):
        self.assertTrue(self.assess([run()])['healthy'])

    def test_no_scheduled_success_alerts(self):
        self.assertIn('NO_SUCCESSFUL_SCHEDULED_RUN', self.assess([])['problems'])

    def test_manual_and_push_success_do_not_hide_stale_schedule(self):
        report = self.assess([run(age=9), run(2, age=0, event='workflow_dispatch'),
                              run(3, age=0, event='push')])
        self.assertIn('SCHEDULED_SUCCESS_OLDER_THAN_8_DAYS', report['problems'])
        self.assertEqual(1, report['last_success']['id'])

    def test_other_branch_workflow_or_fork_is_ineligible(self):
        invalid = [run(branch='feature'), dict(run(), path='other.yml'),
                   dict(run(), head_repository={'id': 11}),
                   dict(run(), repository={'id': 10, 'full_name': 'other/repo'})]
        self.assertIsNone(self.assess(invalid)['last_success'])

    def test_eight_day_boundary_and_future_timestamps(self):
        self.assertTrue(self.assess([run(age=8)])['healthy'])
        self.assertFalse(self.assess([run(age=8.001)])['healthy'])
        self.assertIsNone(self.assess([run(age=-1)])['last_success'])

    def test_latest_failure_alerts_despite_recent_success(self):
        report = self.assess([run(age=2), run(2, age=1, conclusion='failure')])
        self.assertEqual(['LATEST_SCHEDULED_RUN_UNSUCCESSFUL'], report['problems'])

    def test_cancelled_run_alerts_and_later_success_recovers(self):
        runs = [run(1, age=2, conclusion='cancelled')]
        self.assertFalse(self.assess(runs)['healthy'])
        self.assertTrue(self.assess(runs + [run(2)])['healthy'])

    def test_in_progress_does_not_reset_freshness(self):
        report = self.assess([run(age=9), dict(run(2, age=0), status='in_progress', conclusion=None)])
        self.assertIn('SCHEDULED_SUCCESS_OLDER_THAN_8_DAYS', report['problems'])

    @patch.object(m, 'api')
    def test_preview_proposes_without_writing(self, api):
        self.assertEqual('CREATE_ISSUE', m.synchronize(self.assess([]), [], live=False))
        api.assert_not_called()

    @patch.object(m, 'api')
    def test_healthy_without_issue_does_nothing(self, api):
        self.assertEqual('NO_ACTION', m.synchronize(self.assess([run()]), [], live=True))
        api.assert_not_called()

    @patch.object(m, 'api')
    def test_unchanged_alert_does_not_repeat(self, api):
        report = self.assess([])
        self.assertEqual('NO_ACTION', m.synchronize(report, [self.issue(report)], live=True))
        api.assert_not_called()

    @patch.object(m, 'api')
    def test_recovery_preserves_notes_and_requires_human_closure(self, api):
        report = self.assess([run()])
        result = m.synchronize(report, [self.issue(self.assess([]))], live=True)
        self.assertEqual('UPDATE_ISSUE', result)
        payload = api.call_args.kwargs['payload']
        self.assertEqual('open', payload['state'])
        self.assertIn('Human review notes: preserve this decision.', payload['body'])
        self.assertIn('Status: HEALTHY', payload['body'])

    @patch.object(m, 'api')
    def test_closed_issue_reopens_on_problem(self, api):
        report = self.assess([])
        self.assertEqual('REOPEN_ISSUE', m.synchronize(report, [self.issue(report, 'closed')], live=True))

    @patch.object(m, 'api')
    def test_new_live_alert_is_assigned_to_owner(self, api):
        self.assertEqual('CREATE_ISSUE', m.synchronize(self.assess([]), [], live=True))
        self.assertEqual('POST', api.call_args.kwargs['method'])
        self.assertEqual(['neviarrawlinson'], api.call_args.kwargs['payload']['assignees'])

    @patch.object(m, 'api')
    def test_cli_preview_retrieves_and_reports_without_mutations(self, api):
        api.side_effect = [[{'workflow_runs': [run()]}], [[]]]
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
                'GITHUB_REPOSITORY': REPO, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                'GITHUB_REF': 'refs/heads/main', 'GITHUB_STEP_SUMMARY': ''}), \
                patch('sys.argv', ['monitoring', '--output', directory + '/report.json']):
            m.main()
            saved = json.loads(Path(directory, 'report.json').read_text())
            self.assertFalse(saved['live'])
        self.assertTrue(all('method' not in call.kwargs for call in api.call_args_list))

    @patch.object(m, 'api', side_effect=subprocess.CalledProcessError(1, ['gh', 'api']))
    def test_api_failure_does_not_generate_healthy_report_or_write_issue(self, api):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
                'GITHUB_REPOSITORY': REPO, 'GITHUB_EVENT_NAME': 'schedule',
                'GITHUB_REF': 'refs/heads/main'}), \
                patch('sys.argv', ['monitoring', '--live', '--output', directory + '/report.json']):
            with self.assertRaises(subprocess.CalledProcessError):
                m.main()
            self.assertFalse(Path(directory, 'report.json').exists())
        self.assertEqual(1, api.call_count)

    @patch.object(m, 'api')
    def test_duplicate_or_damaged_issues_require_review(self, api):
        report = self.assess([])
        issue = self.issue(report)
        for issues in ([issue, dict(issue, number=8)], [dict(issue, body=m.MARKER)]):
            with self.subTest(issues=issues), self.assertRaises(ValueError):
                m.synchronize(report, issues, live=True)
        api.assert_not_called()

    def test_workflow_uses_main_source_and_preview_default(self):
        root = Path(__file__).resolve().parents[4]
        workflow = yaml.load((root / '.github/workflows/governance-monitoring.yml').read_text(), Loader=yaml.BaseLoader)
        inputs = workflow['on']['workflow_dispatch']['inputs']
        self.assertEqual('preview', inputs['mode']['default'])
        job = workflow['jobs']['monitor']
        self.assertIn("github.event.workflow_run.event == 'schedule'", job['if'])
        self.assertEqual('main', job['steps'][0]['with']['ref'])
        self.assertEqual('false', job['steps'][0]['with']['persist-credentials'])
        self.assertEqual({'actions': 'read', 'contents': 'read'}, workflow['permissions'])
        self.assertEqual('17 7 * * *', workflow['on']['schedule'][0]['cron'])
        monitor = next(step for step in job['steps'] if 'MONITOR_LIVE' in step.get('env', {}))
        self.assertIn("vars.GAC_MONITORING_ENABLED == 'true'", monitor['env']['MONITOR_LIVE'])
        self.assertIn("github.event_name != 'workflow_dispatch'", monitor['env']['MONITOR_LIVE'])


if __name__ == '__main__':
    unittest.main()
