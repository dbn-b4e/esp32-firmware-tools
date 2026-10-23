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
 def test_standard_cpp_header_is_not_a_missing_arduino_library(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r)
   script="from arduino import engine; from pathlib import Path; p=Path(engine.SKETCH_FOLDER)/engine.SKETCH_NAME; p.write_text('#include <atomic>\\n#include <MySensor.h>\\n'); assert engine.extract_includes_from_sketch()==['MySensor.h'], engine.extract_includes_from_sketch()"
   env=dict(os.environ);env['ESP32_BUILD_PROJECT']=str(r)
   p=subprocess.run([sys.executable,'-c',script],cwd=ROOT,env=env,capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr)
 def test_global_help_without_project(self):
  p=subprocess.run([sys.executable,str(ROOT/'build.py'),'--help'],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr);self.assertIn('--project',p.stdout)
 def test_global_help_with_legacy_windows_console_encoding(self):
  env=dict(os.environ);env['PYTHONIOENCODING']='cp1252:strict'
  p=subprocess.run([sys.executable,str(ROOT/'build.py'),'--help'],capture_output=True,text=True,encoding='cp1252',env=env)
  self.assertEqual(p.returncode,0,p.stderr);self.assertIn('--project',p.stdout);self.assertIn('release',p.stdout)
 def test_generic_help_does_not_advertise_project_only_ota(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);p=self.run_cli(r,'--help')
   self.assertEqual(p.returncode,0,p.stderr);self.assertNotIn('--ota',p.stdout)
if __name__=='__main__':unittest.main()
