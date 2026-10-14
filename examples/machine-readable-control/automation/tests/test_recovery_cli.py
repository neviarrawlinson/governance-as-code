import importlib, json, subprocess, sys, tempfile, unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from test_recovery import RecoveryTests

class RecoveryCliTests(RecoveryTests):
 def cli_authorization(self,manifest,today=None):
  today=today or datetime.now(timezone.utc).date();a=self.authorization(manifest);a.update(approved_at=today.isoformat(),valid_until=(today+timedelta(days=3)).isoformat());return a
 def cli(self,*args):
  # Real CLI process, pinned to the original failing regression scenario.
  script="import runpy; from automation import pipeline,recovery; fixture=pipeline.EXAMPLE_ROOT/'test-fixtures/identity-environment-failure.json'; pipeline.ENVIRONMENT_PATH=fixture; recovery.ENVIRONMENT_PATH=fixture; runpy.run_module('automation.recovery_cli',run_name='__main__')"
  return subprocess.run([sys.executable,'-c',script,*map(str,args)],capture_output=True,text=True)
 def test_preview_cli_does_not_publish(self):
  r=self.cli('preview','--evaluation-date','2026-10-13','--output-directory',self.root)
  self.assertEqual(r.returncode,0,r.stderr);self.assertTrue((self.root/'recovery-manifest.json').is_file());self.assertFalse((self.root/'recovery-receipt.json').exists())
 def test_prepare_cli_requires_exact_preview_and_approval(self):
  m=self.preview();a=self.cli_authorization(m);auth=self.root.parent/(self.root.name+'-approval.json');auth.write_text(json.dumps(a));self.addCleanup(auth.unlink)
  output=self.root.parent/(self.root.name+'-publication');self.addCleanup(lambda: __import__('shutil').rmtree(output,ignore_errors=True))
  args=['prepare','--preview-directory',self.root,'--authorization',auth,'--repository','neviarrawlinson/governance-as-code','--branch','main','--actor','neviarrawlinson','--authorization-commit','a'*40,'--promotion-run-id','303','--preview-run-id','101','--preview-artifact-id','202','--output-directory',output]
  r=self.cli(*args);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual({p.name for p in output.iterdir()},{'trusted-assurance-state.json','recovery-receipt.json'})
  a['preview_artifact_id']='999';auth.write_text(json.dumps(a));r=self.cli(*args);self.assertNotEqual(r.returncode,0);self.assertIn('preview',r.stderr.lower())
if __name__=='__main__':unittest.main()

class CalendarRegressionTests(RecoveryCliTests):
 def test_cli_authorization_fixture_remains_valid_in_2030(self):
  m=self.preview()
  self.assertTrue(hasattr(self,'cli_authorization'),'CLI test approval dates must be runtime relative')
  a=self.cli_authorization(m,today=date(2030,1,1))
  self.assertEqual(a['approved_at'],'2030-01-01')
  self.assertGreaterEqual(date.fromisoformat(a['valid_until']),date(2030,1,1))
 def test_real_prepare_cli_with_controlled_2030_clock(self):
  from unittest.mock import patch
  from automation import recovery_cli
  import shutil
  m=self.preview();a=self.cli_authorization(m,today=date(2030,1,1))
  auth=self.root.parent/(self.root.name+'-2030-approval.json');auth.write_text(json.dumps(a));self.addCleanup(auth.unlink)
  output=self.root.parent/(self.root.name+'-2030-publication');self.addCleanup(lambda:shutil.rmtree(output,ignore_errors=True))
  argv=['recovery_cli','prepare','--preview-directory',str(self.root),'--authorization',str(auth),'--repository','neviarrawlinson/governance-as-code','--branch','main','--actor','neviarrawlinson','--authorization-commit','a'*40,'--promotion-run-id','303','--preview-run-id','101','--preview-artifact-id','202','--output-directory',str(output)]
  with patch.object(recovery_cli,'datetime') as clock,patch.object(sys,'argv',argv):
   clock.now.return_value=datetime(2030,1,1,tzinfo=timezone.utc);recovery_cli.main()
  self.assertTrue((output/'recovery-receipt.json').exists())
