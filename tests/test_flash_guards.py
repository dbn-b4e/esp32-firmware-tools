import importlib,os,sys,tempfile,unittest,struct
from pathlib import Path
from unittest.mock import patch
import test_project
ROOT=test_project.ROOT
class FlashGuards(unittest.TestCase):
 def engine(self,root):
  os.environ['ESP32_BUILD_PROJECT']=str(root)
  import esp32_tools.engine as e
  return importlib.reload(e)
 def artifacts(self,root,e):
  from esp32_tools.partitions import parse_layout
  fw=root/'out/images';fw.mkdir(parents=True)
  rows=parse_layout(root/'src/node/partitions.csv',0x400000);subs={'nvs':2,'ota':0,'ota_0':16,'ota_1':17,'spiffs':0x82}
  table=b''.join(struct.pack('<HBBII16sI',0x50aa,0 if k=='app' else 1,subs[s],o,z,n.encode(),0) for n,(k,s,o,z) in rows.items())
  for name,data in [('node.ino.bin',b'app'),('node.ino.bootloader.bin',b'boot'),('node.ino.partitions.bin',table),('boot_app0.bin',bytes(8192))]:(fw/name).write_bytes(data)
  return fw
 def test_oversized_app_rejected_before_device_access(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r);fw=self.artifacts(r,e);(fw/'node.ino.bin').write_bytes(bytes(0x100001))
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'find_boot_app0_path',return_value=str(fw/'boot_app0.bin')),patch('esp32_tools.partitions.validate_device') as device,patch.object(e,'run_command') as write:
    self.assertTrue(e.PARTITIONS_CSV.startswith(str(r)));self.assertFalse(e.flash_firmware('CONFIRMED',str(fw/'node.ino.bin')));device.assert_not_called();write.assert_not_called()
 def test_wrong_compiled_partition_table_rejected_before_device(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r);fw=self.artifacts(r,e);(fw/'node.ino.partitions.bin').write_bytes(b'invalid')
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'find_boot_app0_path',return_value=str(fw/'boot_app0.bin')),patch('esp32_tools.partitions.validate_device') as device,patch.object(e,'run_command') as write:
    self.assertTrue(e.PARTITIONS_CSV.startswith(str(r)));self.assertFalse(e.flash_firmware('CONFIRMED',str(fw/'node.ino.bin')));device.assert_not_called();write.assert_not_called()
 def test_littlefs_size_rejected_before_device(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r);image=r/'wrong.bin';image.write_bytes(b'x')
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'get_partitions',return_value={'littlefs':{'offset':'0x210000'}}),patch('esp32_tools.partitions.validate_device') as device,patch.object(e,'run_command') as write:
    self.assertFalse(e.flash_littlefs('CONFIRMED',str(image)));device.assert_not_called();write.assert_not_called()
 def test_valid_layout_offsets_drive_flash_plan(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r)
   csv=r/'src/node/partitions.csv'
   csv.write_text(csv.read_text().replace('0xe000','0xf000').replace('0x10000,','0x20000,').replace('0x110000','0x120000').replace('0x210000','0x220000'))
   e=self.engine(r);fw=self.artifacts(r,e)
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'find_boot_app0_path',return_value=str(fw/'boot_app0.bin')),patch('esp32_tools.partitions.validate_device'),patch.object(e,'run_command',return_value=True) as write:
    self.assertTrue(e.flash_firmware('CONFIRMED',str(fw/'node.ino.bin')))
    cmd=write.call_args.args[0]
    self.assertEqual(cmd[cmd.index(str(fw/'node.ino.bin'))-1],'0x20000')
    self.assertEqual(cmd[cmd.index(str(fw/'boot_app0.bin'))-1],'0xf000')
 def test_oversized_boot_metadata_rejected_before_device(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r);fw=self.artifacts(r,e);(fw/'boot_app0.bin').write_bytes(bytes(8193))
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'find_boot_app0_path',return_value=str(fw/'boot_app0.bin')),patch('esp32_tools.partitions.validate_device') as device,patch.object(e,'run_command') as write:
    self.assertFalse(e.flash_firmware('CONFIRMED',str(fw/'node.ino.bin')));device.assert_not_called();write.assert_not_called()
if __name__=='__main__':unittest.main()
