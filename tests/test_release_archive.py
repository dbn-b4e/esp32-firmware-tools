import importlib.util,json,struct,tempfile,unittest
from pathlib import Path
import test_project
ROOT=test_project.ROOT

@unittest.skipUnless(importlib.util.find_spec('esptool') and importlib.util.find_spec('detools'),'Optional delta dependencies not installed')
class ReleaseArchiveTests(unittest.TestCase):
 def api(self):
  self.assertIsNotNone(importlib.util.find_spec('release_tools.archive'),'Verified archive packaging missing')
  from release_tools import archive
  return archive
 def profile(self):
  from ota.delta_ota import DeltaProfile
  return DeltaProfile(name='fixture',model='EXAMPLE_C6_V1',envelope_magic=b'ESPDLT1\0',min_base_version=3,slot_size=0x1c0000,manufacturer_code=0x1049,image_type=1)
 def config(self):
  p=self.profile()
  return {'schema_version':1,'name':'fixture','local_inputs':[],'full_ota':{'manufacturer_code':p.manufacturer_code,'image_type':p.image_type,'header_string':p.model,'stack_version':2,'min_hardware_version':1,'max_hardware_version':1,'espressif_compatible':True},'delta_profile':'profile.json'}
 def image(self,path,version,model='EXAMPLE_C6_V1'):
  from esptool.bin_image import ESP32C6FirmwareImage,ImageSegment
  image=ESP32C6FirmwareImage();image.chip_id=13;image.entrypoint=0x40800000
  segment=ImageSegment(0x40800000,struct.pack('<32sI',model.encode(),version)+bytes(range(256))*20);segment.name='.data';image.segments=[segment];image.save(str(path))
 def release(self,root,version,bases=(),legacy_profile=None):
  a=self.api();image=root/f'input-{version}.bin';self.image(image,version)
  dest=root/f'release-{version}';dest.mkdir()
  a.create_full(dest/'full',image,version,self.config(),self.profile())
  deltas=a.create_deltas(dest,image,version,bases,self.config(),self.profile(),legacy_profile)
  metadata={'schema_version':1,'kind':'esp32-release','name':'fixture','version':version,'config':self.config(),'delta_profile':self.profile().as_json(),'deltas':deltas,'source':{'tag':f'v0.0.{version}','commit':'0'*40}}
  a.finalize(dest,metadata);a.verify_release(dest)
  return dest
 def test_full_and_multiple_direct_deltas_are_self_contained(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);base3=self.release(r,3);base4=self.release(r,4);target=self.release(r,5,[base3,base4])
   self.assertEqual(len(a.verify_release(target)['deltas']),2)
   import shutil
   shutil.rmtree(base3);shutil.rmtree(base4)
   self.assertEqual(a.verify_release(target)['version'],5)
   for path in (target/'deltas').iterdir():
    idx=json.loads((path/'z2m-index.json').read_text())[0]
    self.assertEqual(idx['fileVersion'],5);self.assertEqual(idx['minFileVersion'],idx['maxFileVersion'])
 def test_legacy_base_is_verified_and_never_modified(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);image=r/'base.bin';self.image(image,3);base=r/'legacy'
   a.create_full(base,image,3,self.config(),self.profile());before={p.name:p.read_bytes() for p in base.iterdir()}
   target=self.release(r,5,[base],legacy_profile=self.profile());a.verify_release(target)
   self.assertEqual(before,{p.name:p.read_bytes() for p in base.iterdir()})
   app=next(base.glob('*.app.bin'));app.write_bytes(b'corrupt')
   with self.assertRaises(ValueError):a.load_base(base,self.config(),self.profile(),legacy_profile=self.profile())
 def test_different_base_decoder_protocol_is_refused(self):
  a=self.api()
  from dataclasses import replace
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);base=self.release(r,3);image=r/'target.bin';self.image(image,5)
   incompatible=replace(self.profile(),envelope_magic=b'OTHER1\0\0')
   with self.assertRaisesRegex(ValueError,'profile'):a.create_deltas(r/'target',image,5,[base],self.config(),incompatible)
 def test_legacy_base_requires_explicit_decoder_profile(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);image=r/'base.bin';self.image(image,3);base=r/'legacy'
   a.create_full(base,image,3,self.config(),self.profile())
   with self.assertRaisesRegex(ValueError,'legacy'):a.load_base(base,self.config(),self.profile())
 def test_legacy_filesystem_manifest_is_checked_when_present(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);image=r/'base.bin';self.image(image,3);base=r/'legacy'
   a.create_full(base,image,3,self.config(),self.profile())
   (base/'fs.bin').write_bytes(b'truncated')
   (base/'littlefs-manifest.json').write_text(json.dumps({'kind':'filesystem','model':'EXAMPLE_C6_V1','version':3,'size':100,'sha256':'0'*64,'fs_file':'fs.bin'}))
   with self.assertRaisesRegex(ValueError,'filesystem'):a.load_base(base,self.config(),self.profile(),legacy_profile=self.profile())
 def test_corruption_unknown_files_symlinks_and_path_escape_rejected(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);dest=self.release(r,3);m=dest/'release-manifest.json';original=m.read_bytes()
   extra=dest/'unexpected';extra.write_text('extra')
   with self.assertRaises(ValueError):a.verify_release(dest)
   extra.unlink();d=json.loads(original);one=next(iter(d['files']));d['files']['../outside']=d['files'].pop(one);m.write_text(json.dumps(d))
   with self.assertRaises(ValueError):a.verify_release(dest)
   m.write_bytes(original);app=next((dest/'full').glob('*.app.bin'));raw=app.read_bytes();app.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
   with self.assertRaises(ValueError):a.verify_release(dest)
   app.write_bytes(raw)
   import os
   if os.name!='nt':
    other=r/'other';other.write_bytes(raw);app.unlink();app.symlink_to(other)
    with self.assertRaises(ValueError):a.verify_release(dest)
 def test_wrong_model_and_duplicate_or_non_increasing_bases_rejected(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);bad=r/'bad.bin';self.image(bad,5,'OTHER')
   with self.assertRaises(ValueError):a.create_full(r/'bad-full',bad,5,self.config(),self.profile())
   base=self.release(r,3);image=r/'target.bin';self.image(image,5)
   for bases in [[base,base],[self.release(r,5)]]:
    dest=r/('deltas-'+str(len(bases)))
    with self.assertRaises(ValueError):a.create_deltas(dest,image,5,bases,self.config(),self.profile())
if __name__=='__main__':unittest.main()
