import json,os,platform,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];EXAMPLE=ROOT/'examples/c6-zigbee-demo'
class DemoDescriptor(unittest.TestCase):
 def test_real_firmware_header_exports_the_converter_descriptor(self):
  header=EXAMPLE/'sketch/descriptor.h';self.assertTrue(header.is_file(),'Firmware descriptor example missing')
  compiler=shutil.which('c++') or shutil.which('g++') or shutil.which('clang++')
  if not compiler:self.skipTest('Native C++ compiler unavailable; Arduino compilation is validated separately')
  folder=ROOT/'tmp/descriptor-test';folder.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=folder) as t:
   p=Path(t);src=p/'main.cpp';binary=p/('describe.exe' if os.name=='nt' else 'describe')
   src.write_text('#include <stdio.h>\n#include "descriptor.h"\nstruct Sink {void print(const char* s){fputs(s,stdout);} void print(char c){putchar(c);} void print(unsigned n){printf("%u",n);}};\nint main(){Sink s;demo::writeDescriptor(s);}\n')
   flags=['-std=c++17','-I'+str(header.parent)]
   if platform.system()=='Darwin':flags+=['-isysroot',subprocess.check_output(['xcrun','--show-sdk-path'],text=True).strip()]
   subprocess.run([compiler,*flags,str(src),'-o',str(binary)],check=True,capture_output=True,text=True,timeout=30)
   raw=subprocess.check_output([str(binary)],timeout=5)
   from z2m.converter import parse_descriptor,generate
   actual=parse_descriptor(raw);snapshot=json.loads((EXAMPLE/'descriptor.example.json').read_text())
   self.assertEqual(actual,snapshot)
   self.assertEqual(generate(actual),(EXAMPLE/'converter.mjs').read_text())
   self.assertEqual([e['id'] for e in actual['endpoints']],[10,20,30])
if __name__=='__main__':unittest.main()
