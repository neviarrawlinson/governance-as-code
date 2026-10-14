"""Exercise the recovery boundary through real validation and issue planning."""
import hashlib, json, tempfile, unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from automation import pipeline, recovery
from automation.cli import classify_pipeline_status
from automation.state_resolution import resolve_trusted_state
from automation.state_retrieval import validate_recovery_source
from integrations.github.issues import Issue, plan_event_operations

class ReadOnlyIssueGateway:
 def find_open_issue(self,marker):
  return Issue(3,'Synthetic failure','<!-- governance-correlation-id: gac-v1:control-failure:ACP-001-03:USR-004 -->') if 'ACP-001-03:USR-004' in marker else None
 def has_event_marker(self,issue,marker):return False

class RecoveryLifecycleTests(unittest.TestCase):
 def test_absent_history_then_recovery_then_fixture_mfa_remediation(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);metadata=root/'metadata.json';metadata.write_text(json.dumps({'status':'ABSENT'}))
   lineage=pipeline.EXAMPLE_ROOT/'automation/trusted-state-lineage.json'
   resolution=resolve_trusted_state(lineage_path=lineage,retrieval_metadata_path=metadata,state_path=root/'missing',expected_control_id='ACP-001-03',current_evaluation_date=date(2026,10,13))
   self.assertFalse(resolution.issue_operations_allowed)
   observation=pipeline.run_pipeline(date(2026,10,13),root/'blocked',historical_comparison_allowed=False,candidate_state_allowed=False)
   self.assertEqual(classify_pipeline_status(observation,False),'history_unresolved');self.assertIsNone(observation.trusted_state_path)
   preview=root/'preview';m=recovery.build_recovery_candidate(date(2026,10,13),preview)
   a=dict(schema_version='1.0',recovery_id='r1',repository='owner/repo',branch='main',control_id='ACP-001-03',preview_run_id='101',preview_artifact_id='202',source_commit=m['source_commit'],evaluation_date=m['evaluation_date'],candidate_sha256=m['candidate_sha256'],manifest_sha256=recovery.sha256_file(preview/'recovery-manifest.json'),approver='owner',approved_at='2026-10-13',valid_until='2026-10-16',reason='Test-only approval fixture',history_gap_acknowledged=True,review_mode='disclosed_self_review',related_issue=3)
   receipt=recovery.build_recovery_receipt(a,m,promotion_run_id='303',authorization_commit='a'*40,actor='owner')
   run=dict(id=303,head_branch='main',status='completed',conclusion='success',path='.github/workflows/governance-history-recovery.yml',event='workflow_dispatch',head_sha='a'*40,actor={'login':'owner'},repository={'id':10},head_repository={'id':10})
   artifact=dict(id=404,created_at='2026-10-13T12:00:00Z',workflow_run={'id':303})
   state=preview/'trusted-assurance-state.json';validate_recovery_source(receipt,state,source_run=run,artifact=artifact,expected_repository='owner/repo',expected_branch='main')
   metadata.write_text(json.dumps(dict(status='FOUND',source_run_id='303',artifact_id='404',artifact_name='trusted-assurance-state',source_kind='RECOVERY',recovery_receipt_verified=True)))
   resolution=resolve_trusted_state(lineage_path=lineage,retrieval_metadata_path=metadata,state_path=state,expected_control_id='ACP-001-03',current_evaluation_date=date(2026,10,14));self.assertTrue(resolution.historical_comparison_allowed)
   normal=pipeline.run_pipeline(date(2026,10,14),root/'normal',previous_state_path=state)
   event=next(e for e in normal.events if e.subject_id=='USR-004');self.assertEqual(event.event_type,'CONTROL_FAILURE_CONTINUES')
   self.assertEqual([o.operation for o in plan_event_operations(event,ReadOnlyIssueGateway())],['COMMENT_ISSUE'])
   environment=json.loads(pipeline.ENVIRONMENT_PATH.read_text());next(a for a in environment['accounts'] if a['account_id']=='USR-004')['mfa_enabled']=True
   fixture=root/'mfa-fixture.json';fixture.write_text(json.dumps(environment))
   with patch.object(pipeline,'ENVIRONMENT_PATH',fixture):fixed=pipeline.run_pipeline(date(2026,10,15),root/'fixed',previous_state_path=normal.trusted_state_path)
   decision=next(x for x in fixed.decisions if x.subject_id=='USR-004');self.assertEqual((decision.governance_outcome,decision.integrity_status,decision.transition),('PASS','VERIFIED','CONTROL_RECOVERY'))
   event=next(e for e in fixed.events if e.subject_id=='USR-004');ops=plan_event_operations(event,ReadOnlyIssueGateway())
   self.assertEqual([o.operation for o in ops],['COMMENT_ISSUE','CLOSE_ISSUE']);self.assertTrue(all(o.issue_number==3 for o in ops))
if __name__=='__main__':unittest.main()
