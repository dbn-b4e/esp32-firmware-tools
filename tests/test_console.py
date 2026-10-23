import importlib.util,io,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
class ConsoleTests(unittest.TestCase):
 def test_legacy_windows_encoding_does_not_interrupt_operation(self):
  self.assertIsNotNone(importlib.util.find_spec('esp32_tools.console'),'Portable console missing')
  from esp32_tools.console import safe_print
  data=io.BytesIO();stream=io.TextIOWrapper(data,encoding='cp1252')
  safe_print('✅ Flash firmware',file=stream);stream.flush()
  self.assertIn('Flash firmware',data.getvalue().decode('cp1252'))
 def test_unicode_preserved_on_utf8(self):
  self.assertIsNotNone(importlib.util.find_spec('esp32_tools.console'),'Portable console missing')
  from esp32_tools.console import safe_print
  data=io.BytesIO();stream=io.TextIOWrapper(data,encoding='utf-8')
  safe_print('✅ Température',file=stream);stream.flush()
  self.assertEqual(data.getvalue().decode('utf-8'),'✅ Température\n')
