import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml


WORKFLOW = Path(__file__).resolve().parents[4] / '.github/workflows/governance-assurance.yml'


class ExecutionModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
        cls.step = next(step for step in cls.workflow['jobs']['assurance']['steps']
                        if step.get('id') == 'execution-mode')

    def evaluate(self, event, mode='', confirmation=''):
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'outputs'
            summary = Path(directory) / 'summary'
            result = subprocess.run(
                ['bash', '-e', '-c', self.step['run']],
                env={**os.environ, 'EVENT_NAME': event, 'EXECUTION_MODE': mode,
                     'LIVE_CONFIRMATION': confirmation, 'GITHUB_OUTPUT': str(output),
                     'GITHUB_STEP_SUMMARY': str(summary)},
                capture_output=True, text=True,
            )
            values = dict(line.split('=', 1) for line in output.read_text().splitlines())
            return result, values, summary.read_text()

    def test_preview_is_the_manual_default(self):
        inputs = self.workflow['on']['workflow_dispatch']['inputs']
        self.assertEqual('preview', inputs['execution_mode']['default'])
        self.assertEqual(['preview', 'live'], inputs['execution_mode']['options'])
        result, values, summary = self.evaluate('workflow_dispatch', 'preview')
        self.assertEqual(0, result.returncode)
        self.assertEqual('false', values['live_authorized'])
        self.assertIn('Mode: preview', summary)

    def test_automated_events_cannot_authorize_live(self):
        for event in ('push', 'schedule', 'pull_request'):
            with self.subTest(event=event):
                result, values, _ = self.evaluate(event, 'live', 'EXECUTE LIVE ISSUE CHANGES')
                self.assertEqual(0, result.returncode)
                self.assertEqual('false', values['live_requested'])
                self.assertEqual('false', values['live_authorized'])

    def test_live_requires_exact_confirmation(self):
        for confirmation in ('', 'true', 'execute live issue changes',
                             'EXECUTE LIVE ISSUE CHANGES ', '$(touch unexpected-file)'):
            with self.subTest(confirmation=confirmation):
                result, values, _ = self.evaluate('workflow_dispatch', 'live', confirmation)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual('true', values['live_requested'])
                self.assertEqual('false', values['live_authorized'])

    def test_confirmed_live_is_authorized(self):
        result, values, summary = self.evaluate('workflow_dispatch', 'live', 'EXECUTE LIVE ISSUE CHANGES')
        self.assertEqual(0, result.returncode)
        self.assertEqual('true', values['live_authorized'])
        self.assertIn('Mode: live', summary)

    def test_confirmation_alone_does_not_enable_live(self):
        result, values, _ = self.evaluate('workflow_dispatch', 'preview', 'EXECUTE LIVE ISSUE CHANGES')
        self.assertEqual(0, result.returncode)
        self.assertEqual('false', values['live_authorized'])

    def test_unknown_or_missing_manual_mode_fails_closed(self):
        for mode in ('', 'LIVE', 'other'):
            with self.subTest(mode=mode):
                result, values, _ = self.evaluate('workflow_dispatch', mode, 'EXECUTE LIVE ISSUE CHANGES')
                self.assertNotEqual(0, result.returncode)
                self.assertEqual('false', values['live_authorized'])

    def test_live_job_uses_validated_authorization(self):
        job = self.workflow['jobs']['live-governance-workflow']
        self.assertIn("needs.assurance.outputs.live_authorized == 'true'", job['if'])
        execution = next(step for step in job['steps'] if step.get('id') == 'live-execution')
        self.assertEqual('${{ needs.assurance.outputs.live_authorized }}',
                         execution['env']['LIVE_ISSUE_WORKFLOW'])


if __name__ == '__main__':
    unittest.main()
