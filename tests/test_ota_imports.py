"""Both independent OTA CLI and package imports must remain usable."""
import subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class OTAImports(unittest.TestCase):
 def test_delta_import_as_package(self):
  p=subprocess.run([sys.executable,'-c','from ota import delta_ota; p=delta_ota.DeltaProfile("test","TEST_C6",b"TESTDLT1",1,1835008,4169,1); print(p.model)'],capture_output=True,text=True,cwd=ROOT)
  self.assertEqual(p.returncode,0,p.stderr);self.assertIn('TEST_C6',p.stdout)
 def test_full_package_import_and_direct_cli(self):
  from ota.zigbee_ota_generator import build_ota,inspect_ota
  data=build_ota(b'payload',manufacturer_code=4169,image_type=1,file_version=2)
  self.assertEqual(inspect_ota(data)['elements'],[(0,b'payload')])
  p=subprocess.run([sys.executable,str(ROOT/'ota/zigbee_ota_generator.py'),'--help'],capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr);self.assertIn('create',p.stdout)
if __name__=='__main__':unittest.main()
