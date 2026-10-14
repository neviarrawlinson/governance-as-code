import importlib, json, tempfile, unittest
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[4]
class RecoveryWorkflowTests(unittest.TestCase):
 def workflow(self):
  p=ROOT/'.github/workflows/governance-history-recovery.yml';self.assertTrue(p.exists(),'manual recovery workflow missing');return yaml.safe_load(p.read_text())
 def test_preview_default_and_no_issue_write(self):
  w=self.workflow();trigger=w.get('on',w.get(True));self.assertEqual(trigger['workflow_dispatch']['inputs']['mode']['default'],'preview');self.assertEqual(w['permissions']['issues'],'read');self.assertNotIn('issues: write',json.dumps(w))
 def test_shared_concurrency_and_pinned_promotion_source(self):
  w=self.workflow();normal=yaml.safe_load((ROOT/'.github/workflows/governance-assurance.yml').read_text());self.assertEqual(w['concurrency']['group'],normal['concurrency']['group'])
  steps=w['jobs']['recover']['steps'];self.assertTrue(any(s.get('with',{}).get('ref')=='${{ steps.preview-inputs.outputs.source_commit }}' for s in steps));self.assertTrue(any(s.get('with',{}).get('name')=='trusted-assurance-state' and s.get('if')=="${{ inputs.mode == 'promote' && steps.freshness.outputs.ready == 'true' }}" for s in steps))
 def test_preview_wrong_source_and_commit_rejected(self):
  self.assertIsNotNone(importlib.util.find_spec('automation.recovery_workflow'),'recovery admission module missing')
  m=importlib.import_module('automation.recovery_workflow')
  run=dict(id=101,status='completed',conclusion='success',head_branch='main',head_sha='a'*40,path='.github/workflows/governance-history-recovery.yml',event='workflow_dispatch',repository={'id':10},head_repository={'id':10})
  artifact=dict(id=202,name='synthetic-history-recovery-preview-101',expired=False,workflow_run={'id':101,'head_branch':'main','head_sha':'a'*40})
  approval={'preview_run_id':'101','preview_artifact_id':'202','source_commit':'a'*40}
  m.validate_preview_source(approval,run,artifact,branch='main')
  for changes in [dict(head_sha='b'*40),dict(conclusion='failure'),dict(head_branch='other'),dict(path='.github/workflows/other.yml'),dict(head_repository={'id':11})]:
   with self.subTest(changes=changes),self.assertRaises(ValueError):m.validate_preview_source(approval,dict(run,**changes),artifact,branch='main')
 def test_authorization_path_escape_rejected(self):
  self.assertIsNotNone(importlib.util.find_spec('automation.recovery_workflow'),'recovery admission module missing');m=importlib.import_module('automation.recovery_workflow')
  with tempfile.TemporaryDirectory() as d:
   for path in ['../approval.json','/tmp/approval.json','examples/machine-readable-control/recovery/../../fake.json']:
    with self.assertRaises(ValueError):m.authorization_path(Path(d),path)
if __name__=='__main__':unittest.main()
