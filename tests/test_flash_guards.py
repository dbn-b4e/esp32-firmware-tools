import importlib,os,sys,tempfile,unittest,struct
from pathlib import Path
from unittest.mock import patch
import test_project
ROOT=test_project.ROOT
class FlashGuards(unittest.TestCase):
 def engine(self,root):
  os.environ['ESP32_BUILD_PROJECT']=str(root)
  import arduino.engine as e
  return importlib.reload(e)
 def artifacts(self,root,e):
  from arduino.partitions import parse_layout
  fw=root/'out/images';fw.mkdir(parents=True)
  rows=parse_layout(root/'src/node/partitions.csv',0x400000);subs={'nvs':2,'ota':0,'ota_0':16,'ota_1':17,'spiffs':0x82}
  table=b''.join(struct.pack('<HBBII16sI',0x50aa,0 if k=='app' else 1,subs[s],o,z,n.encode(),0) for n,(k,s,o,z) in rows.items())
  for name,data in [('node.ino.bin',b'app'),('node.ino.bootloader.bin',b'boot'),('node.ino.partitions.bin',table),('boot_app0.bin',bytes(8192))]:(fw/name).write_bytes(data)
  return fw
 def test_oversized_app_rejected_before_device_access(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r);fw=self.artifacts(r,e);(fw/'node.ino.bin').write_bytes(bytes(0x100001))
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'find_boot_app0_path',return_value=str(fw/'boot_app0.bin')),patch('arduino.partitions.validate_device') as device,patch.object(e,'run_command') as write:
    self.assertTrue(e.PARTITIONS_CSV.startswith(str(r)));self.assertFalse(e.flash_firmware('CONFIRMED',str(fw/'node.ino.bin')));device.assert_not_called();write.assert_not_called()
 def test_wrong_compiled_partition_table_rejected_before_device(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r);fw=self.artifacts(r,e);(fw/'node.ino.partitions.bin').write_bytes(b'invalid')
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'find_boot_app0_path',return_value=str(fw/'boot_app0.bin')),patch('arduino.partitions.validate_device') as device,patch.object(e,'run_command') as write:
    self.assertTrue(e.PARTITIONS_CSV.startswith(str(r)));self.assertFalse(e.flash_firmware('CONFIRMED',str(fw/'node.ino.bin')));device.assert_not_called();write.assert_not_called()
 def test_littlefs_size_rejected_before_device(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r);image=r/'wrong.bin';image.write_bytes(b'x')
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'get_partitions',return_value={'littlefs':{'offset':'0x210000'}}),patch('arduino.partitions.validate_device') as device,patch.object(e,'run_command') as write:
    self.assertFalse(e.flash_littlefs('CONFIRMED',str(image)));device.assert_not_called();write.assert_not_called()
 def test_valid_layout_offsets_drive_flash_plan(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r)
   csv=r/'src/node/partitions.csv'
   csv.write_text(csv.read_text().replace('0xe000','0xf000').replace('0x10000,','0x20000,').replace('0x110000','0x120000').replace('0x210000','0x220000'))
   e=self.engine(r);fw=self.artifacts(r,e)
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'find_boot_app0_path',return_value=str(fw/'boot_app0.bin')),patch('arduino.partitions.validate_device'),patch.object(e,'run_command',return_value=True) as write:
    self.assertTrue(e.flash_firmware('CONFIRMED',str(fw/'node.ino.bin')))
    cmd=write.call_args.args[0]
    self.assertEqual(cmd[cmd.index(str(fw/'node.ino.bin'))-1],'0x20000')
    self.assertEqual(cmd[cmd.index(str(fw/'boot_app0.bin'))-1],'0xf000')
 def test_oversized_boot_metadata_rejected_before_device(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r);fw=self.artifacts(r,e);(fw/'boot_app0.bin').write_bytes(bytes(8193))
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'find_boot_app0_path',return_value=str(fw/'boot_app0.bin')),patch('arduino.partitions.validate_device') as device,patch.object(e,'run_command') as write:
    self.assertFalse(e.flash_firmware('CONFIRMED',str(fw/'node.ino.bin')));device.assert_not_called();write.assert_not_called()

 def test_device_table_checked_unless_full_erase(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r);fw=self.artifacts(r,e)
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'find_boot_app0_path',return_value=str(fw/'boot_app0.bin')),patch('arduino.partitions.validate_device') as device,patch.object(e,'run_command',return_value=True):
    self.assertTrue(e.flash_firmware('CONFIRMED',str(fw/'node.ino.bin')))
    self.assertTrue(device.call_args.kwargs['check_partition'])
    self.assertTrue(e.flash_firmware('CONFIRMED',str(fw/'node.ino.bin'),erase_mode='all'))
    self.assertFalse(device.call_args.kwargs['check_partition'])
 def test_blank_device_accepted_foreign_table_rejected(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r)
   from arduino import partitions as P
   def fake_run(cmd,**kw):
    class R:returncode=0;stdout='Detected flash size: 4MB';stderr=''
    if 'read-flash' in cmd:Path(cmd[-1]).write_bytes(fake_run.table)
    return R()
   fake_run.table=b'\xff'*0x1000
   with patch('arduino.partitions.subprocess.run',side_effect=fake_run):
    P.validate_device(['esptool'],'PORT',r/'src/node/partitions.csv',r/'out/cache',check_partition=True)
    fake_run.table=struct.pack('<HBBII16sI',0x50aa,0,16,0x20000,0x100000,b'app0',0)+b'\xff'*(0x1000-32)
    with self.assertRaisesRegex(ValueError,'differs|table'):
     P.validate_device(['esptool'],'PORT',r/'src/node/partitions.csv',r/'out/cache',check_partition=True)
 def test_expected_mac_guards_all_writes(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r);fw=self.artifacts(r,e)
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'find_boot_app0_path',return_value=str(fw/'boot_app0.bin')),patch('arduino.partitions.validate_device'),patch.object(e,'read_device_macs',return_value={'58:8c:81:ff:fe:31:1a:34','58:8c:81:31:1a:34'}),patch.object(e,'run_command',return_value=True) as write:
    self.assertFalse(e.flash_firmware('CONFIRMED',str(fw/'node.ino.bin'),expect_mac='aa:bb:cc:dd:ee:ff'));write.assert_not_called()
    self.assertTrue(e.flash_firmware('CONFIRMED',str(fw/'node.ino.bin'),expect_mac='58:8C:81:31:1A:34'))
   image=r/'fs.bin';image.write_bytes(bytes(0x100000))
   with patch.object(e,'find_esptool_path',return_value='esptool'),patch.object(e,'get_partitions',return_value={'littlefs':{'offset':'0x210000'}}),patch('arduino.partitions.validate_device'),patch.object(e,'read_device_macs',return_value={'58:8c:81:31:1a:34'}),patch.object(e,'run_command',return_value=True) as write:
    self.assertFalse(e.flash_littlefs('CONFIRMED',str(image),expect_mac='aa:bb:cc:dd:ee:ff'));write.assert_not_called()
 def test_verify_targets_components_not_merged_image(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r);fw=self.artifacts(r,e);(fw/'node.ino.merged.bin').write_bytes(bytes(0x400000))
   with patch.object(e,'find_boot_app0_path',return_value=str(fw/'boot_app0.bin')),patch.object(e,'verify_flash_against_binary',return_value=True) as v:
    self.assertTrue(e.verify_flashed_components('CONFIRMED',str(fw/'node.ino.merged.bin')))
    targets={(Path(c.args[1]).name,c.args[2] if len(c.args)>2 else c.kwargs['offset']) for c in v.call_args_list}
    self.assertEqual(targets,{('node.ino.bootloader.bin','0x0'),('node.ino.partitions.bin','0x8000'),('node.ino.bin','0x10000')})

 def test_flash_budget_reports_slot_margin_and_warns_near_full(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);test_project.ProjectTests().fixture(r);e=self.engine(r);fw=self.artifacts(r,e)
   self.assertEqual(e.flash_budget(917504,0x100000),{'app':917504,'slot':1048576,'percent':87,'remaining':131072})
   (fw/'node.ino.bin').write_bytes(bytes(995000))
   with patch.object(e,'print_color') as out:
    b=e.report_flash_budget(str(fw/'node.ino.bin'))
    self.assertEqual((b['slot'],b['percent']),(1048576,94))
    text=' '.join(str(c.args[0]) for c in out.call_args_list)
    self.assertIn('995,000',text);self.assertIn('94%',text)
    self.assertTrue(any(c.args[1]=='yellow' for c in out.call_args_list))
   (fw/'node.ino.bin').write_bytes(bytes(100000))
   with patch.object(e,'print_color') as out:
    e.report_flash_budget(str(fw/'node.ino.bin'))
    self.assertTrue(any(c.args[1]=='green' for c in out.call_args_list))
if __name__=='__main__':unittest.main()
