import importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_project
ROOT=test_project.ROOT

def git(root,*args,check=True):
 return subprocess.run(['git','-C',str(root),*args],check=check,capture_output=True,text=True).stdout.strip()
def fixture(root,prefix=''):
 git(root,'init');git(root,'config','user.email','test@example.invalid');git(root,'config','user.name','Fixture')
 project=root/prefix;project.mkdir(parents=True,exist_ok=True);test_project.ProjectTests().fixture(project)
 (root/'.gitignore').write_text('build/\nprivate.h\n')
 (project/'release-config.json').write_text(json.dumps({'schema_version':1,'name':'fixture','local_inputs':[]}))
 git(root,'add','.');git(root,'commit','-m','fixture');git(root,'tag','v1.2.3')
 return project

class ReleaseSourceTests(unittest.TestCase):
 def api(self):
  self.assertIsNotNone(importlib.util.find_spec('release_tools'),'Release orchestration missing')
  from release_tools import source
  return source
 def test_tag_source_wins_over_dirty_checkout_and_semver_must_match(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);p=fixture(r);(p/'src/node/version.h').write_text('#define TEST_FW 0x999999u\n')
   plan=a.make_plan(p,'v1.2.3');self.assertEqual(plan['version'],0x010203)
   self.assertEqual(plan['source']['commit'],git(r,'rev-parse','v1.2.3^{commit}'))
   a.materialize(plan,r/'build/snapshot')
   self.assertIn('0x010203',(r/'build/snapshot/src/node/version.h').read_text())
   git(r,'tag','v1.2.4')
   with self.assertRaisesRegex(ValueError,'version'):a.make_plan(p,'v1.2.4')
   for ref in ['HEAD','main','--help','../v1.2.3']:
    with self.subTest(ref=ref),self.assertRaises(ValueError):a.make_plan(p,ref)
 def test_monorepo_annotated_tag_and_missing_release_config(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);p=fixture(r,'examples/with spaces');git(r,'tag','-a','stable','-m','annotated')
   plan=a.make_plan(p,'stable');self.assertEqual(plan['source']['project_prefix'],'examples/with spaces')
   dest=r/'build/export';a.materialize(plan,dest)
   self.assertTrue((dest/'examples/with spaces/build-config.json').exists())
   (p/'release-config.json').unlink();git(r,'add','-u');git(r,'commit','-m','no release config');git(r,'tag','missing')
   with self.assertRaisesRegex(ValueError,'release-config'):a.make_plan(p,'missing')
 def test_local_inputs_must_be_declared_ignored_files_and_are_fingerprinted(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);p=fixture(r);(p/'private.h').write_text('not-a-real-secret')
   config={'schema_version':1,'name':'fixture','local_inputs':['private.h']}
   (p/'release-config.json').write_text(json.dumps(config));git(r,'add','.');git(r,'commit','-m','local input');git(r,'tag','with-input')
   plan=a.make_plan(p,'with-input');self.assertEqual(plan['local_inputs'][0]['path'],'private.h')
   self.assertNotIn('not-a-real-secret',json.dumps(plan))
   (p/'private.h').write_text('changed-during-build')
   with self.assertRaisesRegex(ValueError,'changed'):a.materialize(plan,r/'build/snapshot')
   for path in ['../outside','src/node/version.h','not-present']:
    config['local_inputs']=[path];(p/'release-config.json').write_text(json.dumps(config));git(r,'add','.');git(r,'commit','-m',path);git(r,'tag','bad'+str(len(path)))
    with self.subTest(path=path),self.assertRaises(ValueError):a.make_plan(p,'bad'+str(len(path)))
 def test_tracked_current_local_input_is_refused_even_if_ignored_in_tag(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);fixture(r);(r/'private.h').write_text('fixture-only')
   (r/'release-config.json').write_text(json.dumps({'schema_version':1,'name':'fixture','local_inputs':['private.h']}))
   git(r,'add','release-config.json');git(r,'commit','-m','input declaration');git(r,'tag','with-input')
   git(r,'add','-f','private.h')
   with self.assertRaisesRegex(ValueError,'tracked'):a.make_plan(r,'with-input')
 def test_tag_object_and_commit_stay_consistent_if_ref_moves(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);fixture(r);git(r,'tag','moving')
   (r/'new-file').write_text('second commit');git(r,'add','.');git(r,'commit','-m','second')
   later=git(r,'rev-parse','HEAD');original=a.git;moved=[]
   def hooked(repo,*args,**kwargs):
    result=original(repo,*args,**kwargs)
    if not moved and args[:2]==('rev-parse','--verify') and args[-1].startswith('refs/tags/moving'):
     moved.append(True);git(r,'tag','-f','moving',later)
    return result
   with patch.object(a,'git',side_effect=hooked):plan=a.make_plan(r,'moving')
   self.assertTrue(moved)
   self.assertEqual(git(r,'rev-parse',plan['source']['tag_object']+'^{commit}'),plan['source']['commit'])
 def test_base_and_legacy_profile_paths_are_relative_to_project_not_process_cwd(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);fixture(r)
   profile=json.loads((ROOT/'ota/examples/esp32c6-profile.json').read_text())
   (r/'profile.json').write_text(json.dumps(profile))
   full={k:profile[k] for k in ['manufacturer_code','image_type','stack_version','min_hardware_version','max_hardware_version']}
   full.update(header_string=profile['model'],espressif_compatible=True)
   (r/'release-config.json').write_text(json.dumps({'schema_version':1,'name':'fixture','local_inputs':[],'full_ota':full,'delta_profile':'profile.json'}))
   git(r,'add','.');git(r,'commit','-m','profile');git(r,'tag','profiled')
   elsewhere=r/'other cwd';elsewhere.mkdir();before=Path.cwd()
   try:
    os.chdir(elsewhere);plan=a.make_plan(r,'profiled',bases=['legacy'],legacy_base_profile='profile.json')
   finally:os.chdir(before)
   self.assertEqual(plan['bases'],[str(r/'legacy')])
 def test_output_confinement_and_existing_destination(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);fixture(r)
   for output in ['../outside','publish','build/../publish']:
    with self.subTest(output=output),self.assertRaises(ValueError):a.make_plan(r,'v1.2.3',output=output)
   (r/'build/present').mkdir(parents=True)
   with self.assertRaisesRegex(ValueError,'exists'):a.make_plan(r,'v1.2.3',output='build/present')
 def test_symlink_in_git_export_is_refused(self):
  a=self.api()
  if os.name=='nt':self.skipTest('Windows symlink creation requires extra privileges')
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);fixture(r);(r/'linked').symlink_to('/outside');git(r,'add','linked');git(r,'commit','-m','link');git(r,'tag','with-link')
   plan=a.make_plan(r,'with-link')
   with self.assertRaisesRegex(ValueError,'link'):a.materialize(plan,r/'build/snapshot')
 def test_submodule_uses_pinned_objects_and_rejects_missing_local_repository(self):
  a=self.api()
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as t:
   r=Path(t);sub=r/'sub';sub.mkdir();git(sub,'init');git(sub,'config','user.email','test@example.invalid');git(sub,'config','user.name','Fixture')
   (sub/'value').write_text('pinned');git(sub,'add','.');git(sub,'commit','-m','pinned')
   parent=r/'parent';parent.mkdir();fixture(parent)
   git(parent,'-c','protocol.file.allow=always','submodule','add',str(sub),'vendor/sub')
   git(parent,'commit','-am','submodule');git(parent,'tag','with-submodule')
   (parent/'vendor/sub/value').write_text('dirty-not-selected')
   plan=a.make_plan(parent,'with-submodule');a.materialize(plan,parent/'build/snapshot')
   self.assertEqual((parent/'build/snapshot/vendor/sub/value').read_text(),'pinned')
   self.assertEqual(len(plan['source']['submodules']),1)
   git(parent,'submodule','deinit','-f','vendor/sub')
   # A deinitialized checkout is still supported through the parent's local module object store.
   a.materialize(a.make_plan(parent,'with-submodule'),parent/'build/second')
if __name__=='__main__':unittest.main()
