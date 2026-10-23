import copy,importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def descriptor():
 return {'schema_version':1,'device':{'model':'C6-TOOLS-DEMO','manufacturer':'Example','description':'BOOT, LED and simulated temperature','firmware_version':65536},'ota':False,'endpoints':[
  {'id':10,'name':'led','clusters':{'input':[0,3,6],'output':[]},'features':[{'type':'on_off'}]},
  {'id':20,'name':'boot','clusters':{'input':[0,3,15],'output':[]},'features':[{'type':'binary_input','property':'pressed'}]},
  {'id':30,'name':'simulated','clusters':{'input':[0,3,1026],'output':[]},'features':[{'type':'temperature'}]}]}
class ConverterTests(unittest.TestCase):
 def api(self):
  self.assertIsNotNone(importlib.util.find_spec('z2m'),'Generic Z2M module missing')
  from z2m import converter
  return converter
 def test_render_uses_exact_identity_and_endpoints_without_mutating_input(self):
  a=self.api();d=descriptor();before=copy.deepcopy(d);code=a.generate(d)
  self.assertEqual(d,before);self.assertIn('fingerprint:',code);self.assertIn('"manufacturerName": "Example"',code)
  self.assertIn('m.deviceEndpoints',code);self.assertIn('"led": 10',code);self.assertIn('"boot": 20',code)
  self.assertIn('m.onOff',code);self.assertIn('m.binary',code);self.assertIn('m.temperature',code);self.assertIn('ota: false',code)
  d['endpoints'].reverse();self.assertEqual(a.generate(d),code)
 def test_bad_identifiers_clusters_and_feature_types_rejected(self):
  a=self.api()
  for change in ('duplicate_id','duplicate_name','bool_id','bad_name','wrong_cluster','unsupported','secret','duplicate_type','wrong_ota','bad_reporting'):
   d=descriptor()
   if change=='duplicate_id':d['endpoints'][1]['id']=10
   if change=='duplicate_name':d['endpoints'][1]['name']='led'
   if change=='bool_id':d['endpoints'][0]['id']=True
   if change=='bad_name':d['endpoints'][0]['name']='x;process.exit()'
   if change=='wrong_cluster':d['endpoints'][1]['clusters']['input']=[6]
   if change=='unsupported':d['endpoints'][0]['features'][0]['type']='custom_arbitrary_javascript'
   if change=='secret':d['wifi_password']='private-data-must-not-be-exported'
   if change=='duplicate_type':d['endpoints'][0]['features'].append({'type':'on_off'})
   if change=='wrong_ota':d['ota']=True
   if change=='bad_reporting':d['endpoints'][2]['features'][0]['reporting']={'min':90,'max':60,'change':10}
   with self.subTest(change=change),self.assertRaises(ValueError):a.generate(d)
 def test_unrepresented_and_custom_server_clusters_are_not_silently_ignored(self):
  a=self.api()
  for cluster in (1026,0xfc00):
   d=descriptor();d['endpoints'][0]['clusters']['input'].append(cluster)
   with self.subTest(cluster=cluster),self.assertRaises(ValueError):a.generate(d)
 def test_strings_are_encoded_as_data(self):
  a=self.api();d=descriptor();payload='quote"; globalThis.injected=true; //'
  d['device']['description']=payload
  self.assertIn(json.dumps(payload),a.generate(d))
 def test_cli_preserves_existing_file_and_rejects_same_input(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   r=Path(t);inp=r/'descriptor.json';out=r/'device.mjs';inp.write_text(json.dumps(descriptor()))
   cmd=[sys.executable,str(ROOT/'z2m/converter.py'),'generate','--input',str(inp),'--output',str(out)]
   p=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr);expected=out.read_bytes()
   p=subprocess.run(cmd,capture_output=True,text=True);self.assertNotEqual(p.returncode,0);self.assertEqual(out.read_bytes(),expected)
   p=subprocess.run(cmd+['--force'],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
   same=cmd.copy();same[-1]=str(inp);p=subprocess.run(same+['--force'],capture_output=True,text=True)
   self.assertNotEqual(p.returncode,0);self.assertEqual(json.loads(inp.read_text()),descriptor())
 def test_duplicate_json_keys_and_oversized_files_rejected(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tests') as t:
   p=Path(t)/'d.json';p.write_text('{"schema_version":1,"schema_version":2}')
   with self.assertRaises(ValueError):a.load_descriptor(p)
   p.write_bytes(b'x'*65537)
   with self.assertRaises(ValueError):a.load_descriptor(p)
if __name__=='__main__':unittest.main()
