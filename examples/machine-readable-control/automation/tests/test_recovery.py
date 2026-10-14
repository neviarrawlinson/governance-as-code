import hashlib, importlib, json, tempfile, unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  from automation import pipeline, recovery
  fixture=pipeline.EXAMPLE_ROOT/'test-fixtures/identity-environment-failure.json'
  for module in (pipeline,recovery):
   patcher=patch.object(module,'ENVIRONMENT_PATH',fixture);patcher.start();self.addCleanup(patcher.stop)
 def module(self):
  self.assertIsNotNone(importlib.util.find_spec('automation.recovery'),'explicit recovery implementation is missing')
  return importlib.import_module('automation.recovery')
 def preview(self):return self.module().build_recovery_candidate(date(2026,10,13),self.root)
 def authorization(self,m):
  return dict(schema_version='1.0',recovery_id='recovery-001',repository='neviarrawlinson/governance-as-code',branch='main',control_id='ACP-001-03',preview_run_id='101',preview_artifact_id='202',source_commit=m['source_commit'],evaluation_date=m['evaluation_date'],candidate_sha256=m['candidate_sha256'],manifest_sha256=self.module().sha256_file(self.root/'recovery-manifest.json'),approver='neviarrawlinson',approved_at='2026-10-13',valid_until='2026-10-16',reason='Reviewed fresh synthetic evidence; history missing.',history_gap_acknowledged=True,review_mode='disclosed_self_review',related_issue=3)
 def validate(self,a,m):self.module().validate_recovery_authorization(a,m,repository='neviarrawlinson/governance-as-code',branch='main',actor='neviarrawlinson',today=date(2026,10,13),manifest_sha256=self.module().sha256_file(self.root/'recovery-manifest.json'))
 def test_preview_preserves_failure_without_transition_or_events(self):
  m=self.preview();s=json.loads((self.root/'trusted-assurance-state.json').read_text());self.assertEqual({x['subject_id']:x['governance_outcome'] for x in s['subjects']}['USR-004'],'FAIL')
  ds=json.loads((self.root/'assurance-decisions.json').read_text());self.assertTrue(all(x['transition'] is None and x['integrity_status']=='VERIFIED' for x in ds));self.assertEqual(list((self.root/'events').glob('*.json')),[])
  self.assertEqual(m['boundary_type'],'EXPLICIT_REBASELINE');self.assertEqual(m['candidate_sha256'],hashlib.sha256((self.root/'trusted-assurance-state.json').read_bytes()).hexdigest());self.assertFalse((self.root/'recovery-receipt.json').exists())
 def test_valid_authorization_and_receipt(self):
  m=self.preview();a=self.authorization(m);self.validate(a,m);r=self.module().build_recovery_receipt(a,m,promotion_run_id='303',authorization_commit='a'*40,actor='neviarrawlinson');self.assertEqual(r['historical_interval_status'],'UNKNOWN');self.assertEqual(r['promotion_run_id'],'303');self.assertEqual(r['authorization'],a)
 def test_missing_and_mismatched_authorization_rejected(self):
  m=self.preview();a=self.authorization(m)
  for key in a:
   bad=dict(a);bad.pop(key)
   with self.subTest(missing=key),self.assertRaises(ValueError):self.validate(bad,m)
  for key,value in [('schema_version','2.0'),('source_commit','b'*40),('candidate_sha256','0'*64),('manifest_sha256','0'*64),('control_id','OTHER'),('evaluation_date','2026-10-12'),('branch','other'),('repository','other/repo'),('approver','other'),('valid_until','2026-10-12'),('approved_at','2026-10-14'),('review_mode','self_review'),('history_gap_acknowledged',False),('related_issue',4),('reason',''),('preview_run_id','../5'),('preview_artifact_id',False)]:
   bad=dict(a);bad[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):self.validate(bad,m)
 def test_evidence_mutation_rejected(self):
  self.preview();next((self.root/'evidence').glob('*.json')).write_text('{}')
  with self.assertRaises(ValueError):self.module().verify_recovery_preview(self.root,today=date(2026,10,13))
 def test_candidate_mutation_rejected(self):
  self.preview();p=self.root/'trusted-assurance-state.json';s=json.loads(p.read_text());s['subjects'][-1]['governance_outcome']='PASS';p.write_text(json.dumps(s))
  with self.assertRaises(ValueError):self.module().verify_recovery_preview(self.root,today=date(2026,10,13))
 def test_future_preview_rejected(self):
  self.preview()
  with self.assertRaises(ValueError):self.module().verify_recovery_preview(self.root,today=date(2026,10,12))
 def test_manifest_path_escape_rejected(self):
  self.preview();p=self.root/'recovery-manifest.json';m=json.loads(p.read_text());m['files']['../escape']='0'*64;p.write_text(json.dumps(m))
  with self.assertRaises(ValueError):self.module().verify_recovery_preview(self.root,today=date(2026,10,13))
 def test_extra_file_rejected(self):
  self.preview();(self.root/'unexpected').write_text('data')
  with self.assertRaises(ValueError):self.module().verify_recovery_preview(self.root,today=date(2026,10,13))
if __name__=='__main__':unittest.main()
