import importlib.util,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Layout(unittest.TestCase):
 def test_backend_and_shared_console_are_separate_packages(self):
  self.assertTrue((ROOT/'arduino/engine.py').is_file(),'Arduino backend folder missing')
  self.assertTrue((ROOT/'common/console.py').is_file(),'Shared console folder missing')
  self.assertFalse((ROOT/'esp32_tools').exists(),'Old ambiguous package remains')
  p=subprocess.run([sys.executable,'-c','from arduino import project,toolchain; from common.console import safe_print; from ota import delta_ota'],cwd=ROOT,capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
if __name__=='__main__':unittest.main()
