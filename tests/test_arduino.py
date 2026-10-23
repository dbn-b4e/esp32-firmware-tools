import importlib.util,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
class ArduinoPaths(unittest.TestCase):
 def api(self):
  self.assertIsNotNone(importlib.util.find_spec('arduino.toolchain'),'Selected-core tool resolver missing')
  from arduino import toolchain as arduino
  return arduino
 def test_selected_core_and_tools_with_spaces(self):
  a=self.api()
  with tempfile.TemporaryDirectory(prefix='tool paths ',dir=ROOT/'tests') as t:
   p=Path(t);platform=p/'hardware/esp32/3.3.4';tool=p/'tools/esptool_py/5.1.0';fs=p/'tools/mklittlefs/4.0'
   for d in [platform/'tools/partitions',tool,fs]:d.mkdir(parents=True)
   (platform/'tools/partitions/boot_app0.bin').write_bytes(b'boot');(tool/'esptool').write_text('');(tool/'esptool.exe').write_text('');(fs/'mklittlefs').write_text('')
   props={'runtime.platform.path':str(platform),'runtime.tools.esptool_py.path':str(tool),'runtime.tools.mklittlefs.path':str(fs)}
   self.assertEqual(a.resolve_tool(props,'esptool_py','posix'),tool/'esptool')
   self.assertEqual(a.resolve_tool(props,'esptool_py','nt'),tool/'esptool.exe')
   self.assertEqual(a.boot_app0(props,'3.3.4'),platform/'tools/partitions/boot_app0.bin')
   with self.assertRaises(ValueError):a.boot_app0(props,'3.3.5')
   with self.assertRaises(ValueError):a.resolve_tool({},'esptool_py','posix')
 def test_property_parser_retains_windows_drive_and_spaces(self):
  a=self.api();p=a.parse_properties('runtime.platform.path=C:\\Arduino Data\\esp32\\3.3.4\nfoo=x=y\n')
  self.assertEqual(p['runtime.platform.path'],'C:\\Arduino Data\\esp32\\3.3.4');self.assertEqual(p['foo'],'x=y')
if __name__=='__main__':unittest.main()
