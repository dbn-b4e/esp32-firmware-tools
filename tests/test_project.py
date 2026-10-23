import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
class ProjectTests(unittest.TestCase):
 def api(self):
  self.assertIsNotNone(importlib.util.find_spec('arduino'),'Shared engine package missing')
  from arduino import project
  return project
 def fixture(self,root):
  (root/'src/node').mkdir(parents=True)
  (root/'src/node/node.ino').write_text('void setup(){} void loop(){}')
  (root/'src/node/version.h').write_text('#define TEST_FW 0x010203u\n')
  (root/'src/node/partitions.csv').write_text('nvs,data,nvs,0x9000,0x5000\notadata,data,ota,0xe000,0x2000\napp0,app,ota_0,0x10000,0x100000\napp1,app,ota_1,0x110000,0x100000\nlittlefs,data,spiffs,0x210000,0x100000\n')
  (root/'libs.txt').write_text('Example==1.0.0\n')
  c={'schema_version':1,'project':'Other project','core':{'id':'esp32:esp32','version':'3.3.4'},'board':{'id':'esp32c6','options':{'FlashSize':'4M','PartitionScheme':'custom'}},'chip':'esp32c6','bootloader_offset':'0x0','version':{'macro':'TEST_FW'},'paths':{'sketch':'src/node','partitions':'src/node/partitions.csv','version_header':'src/node/version.h','requirements':'libs.txt','build':'out/cache','firmware':'out/images'},'upload_baud':921600}
  (root/'build-config.json').write_text(json.dumps(c));return c
 def test_second_project_without_b4e_paths_or_version_macro(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);self.fixture(r);c=a.load_config(r)
   self.assertEqual(a.firmware_version(r,c),(0x010203,'1.2.3'))
   self.assertEqual(a.fqbn(c),'esp32:esp32:esp32c6:FlashSize=4M,PartitionScheme=custom')
   self.assertEqual(a.check_environment(r,c,{'platforms':[{'id':'esp32:esp32','installed_version':'3.3.4'}]})['maximum_size'],0x100000)
   with self.assertRaisesRegex(ValueError,'Core'):a.check_environment(r,c,{'platforms':[{'id':'esp32:esp32','installed_version':'3.3.5'}]})
 def test_escape_and_uncompiled_partition_file_rejected(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);c=self.fixture(r)
   for k,v in [('build','../outside'),('partitions','elsewhere.csv')]:
    b=json.loads(json.dumps(c));b['paths'][k]=v;(r/'build-config.json').write_text(json.dumps(b))
    with self.subTest(key=k),self.assertRaises(ValueError):a.load_config(r)
 def test_overlapping_partitions_rejected(self):
  self.api()
  from arduino.partitions import parse_layout
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);self.fixture(r);p=r/'src/node/partitions.csv';p.write_text(p.read_text().replace('0x110000','0x100000'))
   with self.assertRaisesRegex(ValueError,'overlap|Invalid'):parse_layout(p,0x400000)
 def test_reserved_partition_names_require_correct_types(self):
  self.api()
  from arduino.partitions import parse_layout
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);self.fixture(r);p=r/'src/node/partitions.csv';original=p.read_text()
   for change in [('littlefs,data,spiffs','littlefs,app,ota_1'),('otadata,data,ota','otadata,data,nvs')]:
    p.write_text(original.replace(*change))
    with self.subTest(change=change),self.assertRaises(ValueError):parse_layout(p,0x400000)
if __name__=='__main__':unittest.main()
