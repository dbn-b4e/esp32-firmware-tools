import hashlib,json,os,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_project,test_release_source
ROOT=test_project.ROOT

def components(project,filesystem=None,bad_table=False):
 from arduino.partitions import parse_layout
 out=project/'out/images';out.mkdir(parents=True,exist_ok=True)
 (out/'node.ino.bootloader.bin').write_bytes(b'boot')
 rows=parse_layout(project/'src/node/partitions.csv',0x400000)
 subtypes={'nvs':2,'ota':0,'ota_0':16,'ota_1':17,'spiffs':130}
 table=b''.join(struct.pack('<HBBII16sI',0x50aa,0 if row[0]=='app' else 1,subtypes[row[1]],row[2],row[3],name.encode(),0) for name,row in rows.items())
 (out/'node.ino.partitions.bin').write_bytes(b'bad-table' if bad_table else table)
 if filesystem is not None:(out/'node-littlefs.bin').write_bytes(filesystem)

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
    out=project/'out/images';out.mkdir(parents=True);(out/'node.ino.bin').write_bytes(b'compiled-example');components(project)
    log.write_text('controlled backend success\n')
    return {'libraries':[{'name':'Fixture','version':'1.0.0'}]}
   with patch.object(runner,'run_backend',side_effect=backend):dest=runner.build_release(plan)
   m=archive.verify_release(dest);self.assertEqual(m['version'],0x010203)
   self.assertEqual(m['build']['libraries'][0]['name'],'Fixture')
   self.assertIn('0x999999',(root/'src/node/version.h').read_text())
   self.assertFalse((root/'out').exists())
   with self.assertRaises(ValueError):runner.build_release(plan)
 def test_malformed_filesystem_component_is_rejected(self):
  from release_tools import runner,source
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   root=Path(t);test_release_source.fixture(root);plan=source.make_plan(root,'v1.2.3')
   def backend(project,log):
    out=project/'out/images';out.mkdir(parents=True)
    (out/'node.ino.bin').write_bytes(b'compiled-example')
    (out/'node-littlefs.bin').write_bytes(b'too-short-fs')
    log.write_text('controlled backend');return {}
   with patch.object(runner,'run_backend',side_effect=backend),self.assertRaisesRegex(ValueError,'LittleFS'):runner.build_release(plan)
 def test_changed_version_header_is_rejected_even_without_delta_profile(self):
  from release_tools import runner,source
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   root=Path(t);test_release_source.fixture(root);plan=source.make_plan(root,'v1.2.3')
   def backend(project,log):
    (project/'src/node/version.h').write_text('#define TEST_FW 0x999999u\n')
    out=project/'out/images';out.mkdir(parents=True);(out/'node.ino.bin').write_bytes(b'compiled-example')
    log.write_text('controlled backend');return {}
   with patch.object(runner,'run_backend',side_effect=backend),self.assertRaisesRegex(ValueError,'input changed'):runner.build_release(plan)
 def test_compiled_partition_table_must_match_selected_csv(self):
  from release_tools import runner,source
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   root=Path(t);test_release_source.fixture(root);plan=source.make_plan(root,'v1.2.3')
   def backend(project,log):
    components(project,bad_table=True);(project/'out/images/node.ino.bin').write_bytes(b'compiled-example')
    log.write_text('controlled backend');return {}
   with patch.object(runner,'run_backend',side_effect=backend),self.assertRaisesRegex(ValueError,'table'):runner.build_release(plan)
 def test_standalone_verify_checks_filesystem_semantics_even_if_hashes_updated(self):
  from release_tools import runner,source,archive
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   root=Path(t);test_release_source.fixture(root);plan=source.make_plan(root,'v1.2.3')
   def backend(project,log):
    components(project,filesystem=b'\xff'*0x100000);(project/'out/images/node.ino.bin').write_bytes(b'compiled-example')
    log.write_text('controlled backend');return {}
   with patch.object(runner,'run_backend',side_effect=backend):dest=runner.build_release(plan)
   fs=dest/'components/node-littlefs.bin';fs.write_bytes(b'too-short')
   m=json.loads((dest/'release-manifest.json').read_text());m['files']['components/node-littlefs.bin']={'size':fs.stat().st_size,'sha256':hashlib.sha256(fs.read_bytes()).hexdigest()}
   (dest/'release-manifest.json').write_text(json.dumps(m))
   with self.assertRaisesRegex(ValueError,'LittleFS'):archive.verify_release(dest)
 def test_report_keeps_platform_out_of_compiled_library_list(self):
  from release_tools import runner
  self.assertTrue(hasattr(runner,'parse_libraries'),'Library report parser must distinguish the platform section')
  report='USED LIBRARIES\n----\n  • Zigbee       v3.3.4 /core/Zigbee\nPLATFORM\n----\n  • esp32:esp32  v3.3.4\n'
  self.assertEqual(runner.parse_libraries(report),[{'name':'Zigbee','version':'3.3.4'}])
 def test_backend_failure_never_finalizes_archive_and_logs_remain_private(self):
  from release_tools import runner,source
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   root=Path(t);test_release_source.fixture(root);plan=source.make_plan(root,'v1.2.3')
   def fail(project,log):log.write_text('failure proof');raise ValueError('Backend failed')
   with patch.object(runner,'run_backend',side_effect=fail),self.assertRaisesRegex(ValueError,'Backend failed'):runner.build_release(plan)
   dest=Path(plan['output']);self.assertFalse((dest/'release-manifest.json').exists())
   logs=list((root/'build/release-work').glob('*/build.log'));self.assertEqual(len(logs),1)
   if os.name!='nt':self.assertEqual(logs[0].stat().st_mode&0o077,0)
class ToolPinTests(unittest.TestCase):
 def test_tagged_tools_submodule_must_match_running_engine(self):
  from release_tools import runner
  from release_tools.runner import check_tool_pin,TOOLS
  import subprocess
  head=subprocess.run(['git','-C',str(TOOLS),'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
  previous=subprocess.run(['git','-C',str(TOOLS),'rev-parse','HEAD~1'],capture_output=True,text=True).stdout.strip()
  def plan(commit):return {'source':{'submodules':[{'path':'tools/engine','commit':commit,'repository':str(TOOLS)}]}}
  check_tool_pin(plan(head))  # pinned commit equals the running engine
  with self.assertRaisesRegex(ValueError,'differs from the running engine'):check_tool_pin(plan(previous))
  check_tool_pin(plan(previous),allow_mismatch=True)
  # A submodule that is not the engine (no release_tools/cli.py at that commit) is never checked.
  check_tool_pin({'source':{'submodules':[{'path':'libs/other','commit':'0'*40,'repository':str(TOOLS)}]}})

if __name__=='__main__':unittest.main()
