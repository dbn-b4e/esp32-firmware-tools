import importlib.util,json,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from test_z2m_converter import descriptor
class Stream:
 def __init__(self,data):self.data=data;self.requests=[]
 def read(self,n):
  if self.data:r,self.data=self.data[:17],self.data[17:];return r
  time.sleep(.001);return b''
 def write(self,data):self.requests.append(data);return len(data)
class CaptureTests(unittest.TestCase):
 def api(self):
  self.assertIsNotNone(importlib.util.find_spec('z2m.serial_capture'),'Serial descriptor adapter missing')
  from z2m import serial_capture
  return serial_capture
 def test_noise_is_discarded_and_partial_frames_reassembled(self):
  a=self.api();stream=Stream(b'boot log\nwifi_password=must_not_be_saved\nZ2M_DESCRIPTOR '+json.dumps(descriptor()).encode()+b'\r\n')
  result=a.read_descriptor(stream,timeout=.5)
  self.assertEqual(result['device']['model'],'C6-TOOLS-DEMO');self.assertNotIn('wifi_password',json.dumps(result))
  self.assertEqual(stream.requests,[b'describe\n'])
 def test_missing_or_invalid_descriptor_times_out(self):
  a=self.api()
  for data in [b'only logs\n',b'Z2M_DESCRIPTOR {"wifi_password":"private"}\n',b'x'*70000+b'\n']:
   with self.subTest(size=len(data)),self.assertRaises(ValueError):a.read_descriptor(Stream(data),timeout=.03)
if __name__=='__main__':unittest.main()
