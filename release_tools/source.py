"""Resolve local Git tags and export exact trees without changing a checkout."""
import hashlib,io,json,os,re,subprocess,tarfile
from pathlib import Path
from .config import relative,inside,release_config,delta_profile,json_data
from ota.zigbee_ota_generator import require


def git(repo,*args,check=True):
    r=subprocess.run(['git','-C',str(repo),*args],capture_output=True,timeout=90)
    if check:require(r.returncode==0,'Git operation failed: '+args[0])
    return r


def blob(repo,commit,name):
    name=relative(name)
    r=git(repo,'show',commit+':'+name,check=False)
    require(r.returncode==0,'Missing tagged file: '+name)
    return r.stdout


def ignored(repo,path):
    rel=Path(path).relative_to(repo).as_posix()
    return git(repo,'check-ignore','--no-index','-q','--',rel,check=False).returncode==0


def local_module(repo,path,commit):
    # git submodule deinit keeps the object database; no network or checkout needed.
    candidate=inside(repo,path)
    if (candidate/'.git').exists() and git(candidate,'cat-file','-e',commit+'^{commit}',check=False).returncode==0:return candidate
    gitdir=Path(os.fsdecode(git(repo,'rev-parse','--absolute-git-dir').stdout).strip())
    candidate=inside(gitdir/'modules',path)
    require(candidate.is_dir() and git(candidate,'cat-file','-e',commit+'^{commit}',check=False).returncode==0,
            'Missing local submodule objects: '+path+'; initialize/fetch the pinned submodule explicitly')
    return candidate


def submodules(repo,commit,prefix='',depth=0):
    require(depth<=8,'Submodule nesting exceeds supported depth')
    result=[]
    for row in git(repo,'ls-tree','-rz',commit).stdout.split(b'\0'):
        if not row:continue
        metadata,name=row.split(b'\t',1);mode,kind,oid=metadata.decode().split()
        if mode!='160000':continue
        name=relative(os.fsdecode(name));sha=oid;local=local_module(repo,name,sha)
        path='/'.join(x for x in [prefix,name] if x)
        result.append({'path':path,'commit':sha,'repository':str(local)})
        result.extend(submodules(local,sha,path,depth+1))
    return result


def tagged_file(repo,commit,name,modules):
    for m in sorted(modules,key=lambda x:len(x['path']),reverse=True):
        if name.startswith(m['path']+'/'):
            return blob(m['repository'],m['commit'],name[len(m['path'])+1:])
    return blob(repo,commit,name)


def make_plan(project,ref,output=None,bases=(),legacy_base_profile=None):
    project=Path(project).resolve()
    repo=Path(os.fsdecode(git(project,'rev-parse','--show-toplevel').stdout).strip()).resolve()
    prefix=project.relative_to(repo).as_posix();prefix='' if prefix=='.' else prefix
    require(isinstance(ref,str) and not ref.startswith('-') and '..' not in ref,'Expected a local Git tag')
    require(git(repo,'check-ref-format','refs/tags/'+ref,check=False).returncode==0,'Invalid tag name')
    tag='refs/tags/'+ref
    tag_object=os.fsdecode(git(repo,'rev-parse','--verify',tag,check=False).stdout).strip()
    require(re.fullmatch(r'[0-9a-f]{40,64}',tag_object),'Local tag not found: '+ref)
    commit=os.fsdecode(git(repo,'rev-parse','--verify',tag_object+'^{commit}',check=False).stdout).strip()
    require(re.fullmatch(r'[0-9a-f]{40,64}',commit),'Tag does not point to a commit: '+ref)
    modules=submodules(repo,commit)
    def read(name):return tagged_file(repo,commit,'/'.join(x for x in [prefix,relative(name)] if x),modules)
    c=release_config(read('release-config.json'));build=json_data(read('build-config.json'))
    require(isinstance(build,dict) and build.get('schema_version')==1,'Invalid tagged build configuration')
    require(isinstance(build.get('paths'),dict) and isinstance(build.get('version'),dict),'Missing tagged build paths/version')
    for name in build['paths'].values():relative(name)
    macro=build['version'].get('macro');require(isinstance(macro,str) and re.fullmatch(r'[A-Za-z_]\w*',macro),'Invalid version macro')
    text=read(build['paths']['version_header']).decode()
    versions=re.findall(r'^\s*#define\s+'+re.escape(macro)+r'\s+(0x[0-9a-fA-F]+|\d+)[uU]?\s*$',text,re.M)
    require(len(versions)==1,'Version macro must be defined exactly once')
    version=int(versions[0],0);require(0<=version<=0xffffffff,'Invalid uint32 version')
    version_text=f'{version>>16}.{(version>>8)&255}.{version&255}'
    if re.fullmatch(r'v?\d+\.\d+(?:\.\d+)?',ref):
        parts=[int(x) for x in ref.lstrip('v').split('.')];parts+=[] if len(parts)==3 else [0]
        require(parts==[version>>16,(version>>8)&255,version&255],'Tag version differs from tagged firmware version')
    output=output or 'build/releases/'+c['name']+'/v'+version_text
    destination=inside(project,str(output))
    scratch=inside(project,'build/release-work')
    require(not destination.is_relative_to(scratch) and not scratch.is_relative_to(destination),'Release output overlaps private scratch')
    require(ignored(repo,destination),'Release output must be ignored by Git')
    require(not destination.exists(),'Release output already exists')
    require(ignored(repo,project/'build/release-work'),'Scratch build/release-work must be ignored by Git')
    inputs=[]
    for name in c['local_inputs']:
        path=inside(project,name)
        require(path.is_file() and ignored(repo,path),'Local input must exist and be ignored: '+name)
        require(not git(repo,'ls-files','--',path.relative_to(repo).as_posix()).stdout.strip(),'Local input is tracked in the current checkout: '+name)
        selected='/'.join(x for x in [prefix,name] if x)
        tracked=git(repo,'ls-tree','-r','--name-only',commit,'--',selected).stdout.strip()
        require(not tracked,'Local input must not replace tracked source: '+name)
        inputs.append({'path':name,'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    profile=None
    if 'delta_profile' in c:
        require(build.get('chip')=='esp32c6','Differential validation supports ESP32-C6 only')
        profile=delta_profile(read(c['delta_profile']),c['full_ota']).as_json()
    require(not bases or profile is not None,'Base releases require a compatible delta profile')
    legacy=None
    if legacy_base_profile is not None:
        require(profile is not None,'A legacy declaration needs a target delta profile')
        legacy_path=Path(legacy_base_profile)
        if not legacy_path.is_absolute():legacy_path=project/legacy_path
        legacy=delta_profile(legacy_path.read_bytes(),c['full_ota']).as_json()
        require(legacy==profile,'Declared legacy decoder profile differs from target profile')
    return {'schema_version':1,'project_root':str(project),'source':{'repository':str(repo),'tag':ref,
            'tag_object':tag_object,'commit':commit,
            'project_prefix':prefix,'submodules':modules},'config':c,'build_config':build,
            'version':version,'version_text':version_text,'output':str(destination),
            'local_inputs':inputs,'delta_profile':profile,'legacy_base_profile':legacy,'bases':[str((Path(b) if Path(b).is_absolute() else project/Path(b)).resolve()) for b in bases]}


def export_tree(repo,commit,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    raw=git(repo,'archive','--format=tar',commit).stdout
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        for item in archive:
            name=item.name.rstrip('/')
            if not name:continue
            path=inside(destination,name)
            require(not item.issym() and not item.islnk(),'Git export contains a link')
            require(item.isdir() or item.isfile(),'Unsupported Git archive entry')
            if item.isdir():path.mkdir(parents=True,exist_ok=True,mode=0o700)
            else:
                path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                with path.open('xb') as f:
                    source=archive.extractfile(item)
                    while data:=source.read(1024*1024):f.write(data)
                path.chmod(0o700 if item.mode&0o111 else 0o600)


def materialize(plan,destination):
    destination=Path(destination)
    require(not destination.exists(),'Snapshot destination already exists')
    source=plan['source'];export_tree(source['repository'],source['commit'],destination)
    for m in source['submodules']:export_tree(m['repository'],m['commit'],inside(destination,m['path']))
    project=destination/source['project_prefix']
    for item in plan['local_inputs']:
        data=inside(plan['project_root'],item['path']).read_bytes()
        require(len(data)==item['size'] and hashlib.sha256(data).hexdigest()==item['sha256'],'Local input changed after planning: '+item['path'])
        target=inside(project,item['path']);require(not target.exists(),'Local input collides with tagged file')
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);target.write_bytes(data);target.chmod(0o600)
    return project
