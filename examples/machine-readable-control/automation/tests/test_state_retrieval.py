import io, importlib, json, tempfile, unittest, zipfile
from datetime import date
from pathlib import Path

class RetrievalTests(unittest.TestCase):
 def module(self):
  self.assertIsNotNone(importlib.util.find_spec('automation.state_retrieval'),'receipt-aware retrieval missing');return importlib.import_module('automation.state_retrieval')
 def run(self,result=None):return super().run(result)
 def source(self,kind='normal',**changes):
  r=dict(id=1,head_branch='main',status='completed',conclusion='success',path='.github/workflows/'+('governance-assurance.yml' if kind=='normal' else 'governance-history-recovery.yml'),event='workflow_dispatch',head_sha='a'*40,actor={'login':'owner'},repository={'id':10},head_repository={'id':10},created_at='2026-10-13T12:00:00Z');r.update(changes);return r
 def artifact(self,**changes):
  a=dict(id=2,name='trusted-assurance-state',expired=False,created_at='2026-10-13T12:10:00Z',workflow_run={'id':1,'head_branch':'main','head_sha':'a'*40});a.update(changes);return a
 def test_select_newest_successful_normal_and_recovery(self):
  m=self.module();r=self.source('recovery');a=self.artifact();self.assertEqual(m.select_trusted_state([r],[a],branch='main',current_run_id='9')['source_kind'],'RECOVERY')
  self.assertEqual(m.select_trusted_state([self.source()],[a],branch='main',current_run_id='9')['source_kind'],'NORMAL')
 def test_reject_ineligible_sources(self):
  m=self.module()
  for changes in [dict(conclusion='failure'),dict(status='in_progress'),dict(head_branch='other'),dict(path='.github/workflows/fake.yml'),dict(head_repository={'id':11})]:
   with self.subTest(changes=changes):self.assertIsNone(m.select_trusted_state([self.source(**changes)],[self.artifact()],branch='main',current_run_id='9'))
  self.assertIsNone(m.select_trusted_state([self.source()],[self.artifact(expired=True)],branch='main',current_run_id='9'))
  self.assertIsNone(m.select_trusted_state([self.source()],[self.artifact()],branch='main',current_run_id='1'))
 def archive(self,names):
  f=io.BytesIO()
  with zipfile.ZipFile(f,'w') as z:
   for name,data in names:z.writestr(name,data)
  return f.getvalue()
 def test_archive_traversal_duplicate_and_oversize_rejected(self):
  m=self.module()
  for data in [self.archive([('../evil','x')]),self.archive([('/absolute','x')]),self.archive([('a','x'),('a','y')]),self.archive([('large','x'*(10*1024*1024+1))]),b'not zip']:
   with tempfile.TemporaryDirectory() as d,self.subTest(size=len(data)),self.assertRaises(ValueError):m.extract_bounded_zip(data,Path(d))
 def test_valid_archive_extracts(self):
  with tempfile.TemporaryDirectory() as d:
   self.module().extract_bounded_zip(self.archive([('state.json','{}')]),Path(d));self.assertEqual((Path(d)/'state.json').read_text(),'{}')
 def test_freshness_rejects_newer_or_same_date_conflicting_state(self):
  m=self.module();candidate={'evaluation_date':'2026-10-13','candidate_sha256':'0'*64}
  for previous in [dict(evaluation_date='2026-10-14',candidate_sha256='0'*64),dict(evaluation_date='2026-10-13',candidate_sha256='1'*64)]:
   with self.assertRaises(ValueError):m.check_candidate_freshness(candidate,previous)
  self.assertTrue(m.check_candidate_freshness(candidate,dict(evaluation_date='2026-10-12',candidate_sha256='1'*64)))
  self.assertFalse(m.check_candidate_freshness(candidate,dict(evaluation_date='2026-10-13',candidate_sha256='0'*64)))
 def test_receipt_missing_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'trusted-assurance-state.json';p.write_text('{}')
   with self.assertRaises(ValueError):self.module().validate_recovery_source({},p,source_run=self.source('recovery'),artifact=self.artifact(),expected_repository='owner/repo',expected_branch='main')
if __name__=='__main__':unittest.main()

class ReceiptValidationTests(unittest.TestCase):
 def test_valid_receipt_and_tampering(self):
  import importlib
  self.assertIsNotNone(importlib.util.find_spec('automation.state_retrieval'),'receipt validator missing')
  from automation import recovery, state_retrieval as retrieval
  import copy
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);m=recovery.build_recovery_candidate(date(2026,10,13),root)
   a=dict(schema_version='1.0',recovery_id='r1',repository='owner/repo',branch='main',control_id='ACP-001-03',preview_run_id='101',preview_artifact_id='202',source_commit=m['source_commit'],evaluation_date=m['evaluation_date'],candidate_sha256=m['candidate_sha256'],manifest_sha256=recovery.sha256_file(root/'recovery-manifest.json'),approver='owner',approved_at='2026-10-13',valid_until='2026-10-16',reason='Reviewed synthetic baseline',history_gap_acknowledged=True,review_mode='disclosed_self_review',related_issue=3)
   receipt=recovery.build_recovery_receipt(a,m,promotion_run_id='1',authorization_commit='a'*40,actor='owner')
   run=RetrievalTests().source('recovery');artifact=RetrievalTests().artifact()
   def validate(r=receipt,s=run):retrieval.validate_recovery_source(r,root/'trusted-assurance-state.json',source_run=s,artifact=artifact,expected_repository='owner/repo',expected_branch='main')
   validate()
   for key,value in [('promotion_run_id','99'),('executed_by','stranger'),('authorization_commit','b'*40),('historical_interval_status','KNOWN')]:
    bad=copy.deepcopy(receipt);bad[key]=value
    with self.subTest(key=key),self.assertRaises(ValueError):validate(bad)
   bad=copy.deepcopy(receipt);bad['authorization']['approver']='stranger'
   with self.assertRaises(ValueError):validate(bad)
   run2=dict(run,path='.github/workflows/other.yml')
   with self.assertRaises(ValueError):validate(s=run2)

class RetrievalApiTests(unittest.TestCase):
 def test_retrieval_distinguishes_absent_expired_ineligible_unavailable(self):
  from unittest.mock import patch
  from automation import state_retrieval as m
  helper=RetrievalTests()
  cases=[([],[],'ABSENT'),([helper.source()],[helper.artifact(expired=True)],'EXPIRED'),([helper.source(conclusion='failure')],[helper.artifact()],'INELIGIBLE')]
  for runs,artifacts,status in cases:
   with tempfile.TemporaryDirectory() as d,patch.object(m,'gh_json',side_effect=[[{'workflow_runs':runs}],[{'artifacts':artifacts}]]):
    result=m.retrieve_trusted_state('owner/repo','main','9',Path(d));self.assertEqual(result['status'],status)
  with tempfile.TemporaryDirectory() as d,patch.object(m,'gh_json',side_effect=OSError('offline')):
   self.assertEqual(m.retrieve_trusted_state('owner/repo','main','9',Path(d))['status'],'UNAVAILABLE')
 def test_normal_retrieval_and_corrupt_newest_do_not_roll_back(self):
  from unittest.mock import patch
  from automation import state_retrieval as m
  import hashlib
  helper=RetrievalTests();state={'control_id':'ACP-001-03','evaluation_date':'2026-10-13','subjects':[{'subject_id':'USR-004','governance_outcome':'FAIL'}]}
  data=helper.archive([('trusted-assurance-state.json',json.dumps(state))]);artifact=helper.artifact(digest='sha256:'+hashlib.sha256(data).hexdigest())
  for archive,status in [(data,'FOUND'),(b'corrupted','INVALID')]:
   with tempfile.TemporaryDirectory() as d,patch.object(m,'gh_json',side_effect=[[{'workflow_runs':[helper.source()]}],[{'artifacts':[artifact]}]]),patch.object(m,'gh_archive',return_value=archive):
    result=m.retrieve_trusted_state('owner/repo','main','9',Path(d));self.assertEqual(result['status'],status)

class DownloadDeadlineTests(unittest.TestCase):
 def test_stalled_child_is_killed_before_deadline(self):
  from unittest.mock import patch
  from automation import state_retrieval as m
  import subprocess, sys, time
  original=subprocess.Popen;children=[]
  def child(*args,**kwargs):
   p=original([sys.executable,'-c','import time; time.sleep(1)'],**kwargs);children.append(p);return p
  start=time.monotonic()
  with patch.object(m.subprocess,'Popen',side_effect=child),patch.object(m,'DOWNLOAD_TIMEOUT',0.05,create=True):
   with self.assertRaisesRegex(ValueError,'timed out'):m.gh_archive('unused')
  self.assertLess(time.monotonic()-start,0.5)
  self.assertTrue(children and all(p.poll() is not None for p in children))
