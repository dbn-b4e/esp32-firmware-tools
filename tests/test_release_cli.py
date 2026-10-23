import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_project,test_release_source
ROOT=test_project.ROOT

class ReleaseCLITests(unittest.TestCase):
 def cli(self,project,*args):
  env=dict(os.environ);env['PATH']=''
  return subprocess.run([sys.executable,str(ROOT/'build.py'),'--project',str(project),'release',*args],capture_output=True,text=True,env=env)
 def test_plan_and_help_need_no_arduino_and_verify_missing_is_refused(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   root=Path(t);test_release_source.fixture(root)
   # Keep Git available while making any accidental Arduino execution fail.
   env=dict(os.environ)
   cmd=[sys.executable,str(ROOT/'build.py'),'--project',str(root),'release','plan','--ref','v1.2.3']
   p=subprocess.run(cmd,capture_output=True,text=True,env=env)
   self.assertEqual(p.returncode,0,p.stderr);d=json.loads(p.stdout);self.assertEqual(d['version'],0x010203)
   self.assertFalse((root/'build').exists())
   help=self.cli(root,'--help');self.assertEqual(help.returncode,0,help.stderr);self.assertIn('verify',help.stdout)
   missing=self.cli(root,'verify','--archive','build/missing');self.assertNotEqual(missing.returncode,0)
 def test_successful_backend_build_is_archived_and_checkout_is_untouched(self):
  from release_tools import runner,source,archive
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   root=Path(t);test_release_source.fixture(root)
   (root/'src/node/version.h').write_text('#define TEST_FW 0x999999u\n')
   plan=source.make_plan(root,'v1.2.3')
   def backend(project,log):
    # Test only the compiler boundary; source export and archive verification are real.
    self.assertIn('0x010203',(project/'src/node/version.h').read_text())
    out=project/'out/images';out.mkdir(parents=True);(out/'node.ino.bin').write_bytes(b'compiled-example')
    log.write_text('controlled backend success\n')
    return {'libraries':[{'name':'Fixture','version':'1.0.0'}]}
   with patch.object(runner,'run_backend',side_effect=backend):dest=runner.build_release(plan)
   m=archive.verify_release(dest);self.assertEqual(m['version'],0x010203)
   self.assertEqual(m['build']['libraries'][0]['name'],'Fixture')
   self.assertIn('0x999999',(root/'src/node/version.h').read_text())
   self.assertFalse((root/'out').exists())
   with self.assertRaises(ValueError):runner.build_release(plan)
 def test_backend_failure_never_finalizes_archive_and_logs_remain_private(self):
  from release_tools import runner,source
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   root=Path(t);test_release_source.fixture(root);plan=source.make_plan(root,'v1.2.3')
   def fail(project,log):log.write_text('failure proof');raise ValueError('Backend failed')
   with patch.object(runner,'run_backend',side_effect=fail),self.assertRaisesRegex(ValueError,'Backend failed'):runner.build_release(plan)
   dest=Path(plan['output']);self.assertFalse((dest/'release-manifest.json').exists())
   logs=list((root/'build/release-work').glob('*/build.log'));self.assertEqual(len(logs),1)
   if os.name!='nt':self.assertEqual(logs[0].stat().st_mode&0o077,0)
if __name__=='__main__':unittest.main()
