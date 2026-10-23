import os,subprocess,sys,tempfile,unittest
from pathlib import Path
import test_project
ROOT=test_project.ROOT

class CLITests(unittest.TestCase):
 def run_cli(self,root,*args):
  env=dict(os.environ);env['PATH']=''
  return subprocess.run([sys.executable,str(ROOT/'build.py'),'--project',str(root),*args],capture_output=True,text=True,env=env)
 def test_second_project_info_uses_configured_output_and_version(self):
  with tempfile.TemporaryDirectory(prefix='project with spaces ',dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);p=self.run_cli(r,'--info')
   self.assertEqual(p.returncode,0,p.stderr);self.assertIn('1.2.3',p.stdout)
   self.assertIn(str(r/'out/images'),p.stdout);self.assertNotIn('B4E ESP32-C6',p.stdout)
 def test_flash_without_port_rejected_without_external_tools(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);p=self.run_cli(r,'--flash')
   self.assertNotEqual(p.returncode,0);self.assertIn('Explicit --port required',p.stderr)
 def test_help_does_not_run_arduino(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);p=self.run_cli(r,'--help')
   self.assertEqual(p.returncode,0,p.stderr);self.assertIn('--check-environment',p.stdout)
if __name__=='__main__':unittest.main()
