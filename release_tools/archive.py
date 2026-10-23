"""Verified self-contained release archives; reuse the existing OTA protocol."""
import hashlib,json,struct
from pathlib import Path
from .config import inside,relative,json_data,release_config,delta_profile
from ota.zigbee_ota_generator import build_ota,inspect_ota,require,uint

MAX_FILE=64*1024*1024


def digest(data):return hashlib.sha256(data).hexdigest()


def read(root,name,limit=MAX_FILE):
    p=inside(root,name)
    require(p.is_file() and p.stat().st_size<=limit,'Missing or oversized artifact: '+name)
    return p.read_bytes()


def write(root,name,data):
    p=inside(root,name);p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with p.open('xb') as f:f.write(data)
    p.chmod(0o600)


def encode(value):return (json.dumps(value,indent=2,ensure_ascii=True)+'\n').encode()


def app_check(data,version,profile):
    uint(version,32,'firmware version')
    require(0<len(data)<=MAX_FILE,'Invalid application size')
    if profile is not None:
        from ota.delta_ota import esp_digest
        require(len(data)<=profile.slot_size,'Application exceeds profile slot size')
        require(struct.pack('<32sI',profile.model.encode(),version) in data,'Compiled model/version marker absent')
        esp_digest(data)


def full_manifest(app,version,config,app_name,ota_name=None):
    full=config.get('full_ota')
    m={'kind':'firmware','model':full['header_string'] if full else config['name'],
       'version':version,'size':len(app),'sha256':digest(app),'app_file':app_name}
    if full:
        ota=build_ota(app,file_version=version,**full)
        m.update(zigbee_file=ota_name,manufacturer_code=full['manufacturer_code'],image_type=full['image_type'],zigbee_sha512=hashlib.sha512(ota).hexdigest())
    return m


def index(full,ota,version,name):
    return [dict(fileVersion=version,fileSize=len(ota),manufacturerCode=full['manufacturer_code'],
                 imageType=full['image_type'],sha512=hashlib.sha512(ota).hexdigest(),url=name)]


def create_full(directory,image,version,config,profile=None):
    directory=Path(directory);app=Path(image).read_bytes();app_check(app,version,profile)
    require(not directory.exists() and not directory.is_symlink(),'Full output already exists')
    app_name=config['name']+'.app.bin';ota_name=config['name']+f'-{version:08x}.ota'
    m=full_manifest(app,version,config,app_name,ota_name)
    directory.mkdir(parents=True,mode=0o700);write(directory,app_name,app)
    if config.get('full_ota'):
        ota=build_ota(app,file_version=version,**config['full_ota']);inspect_ota(ota)
        write(directory,ota_name,ota);write(directory,'z2m-index.json',encode(index(config['full_ota'],ota,version,ota_name)))
    write(directory,'ota-manifest.json',encode(m));verify_full(directory,config,profile)
    return m


def verify_full(directory,config,profile=None):
    m=json_data(read(directory,'ota-manifest.json',4*1024*1024))
    require(isinstance(m,dict),'Invalid full manifest')
    try:
        app_name=m['app_file'];require(Path(app_name).name==app_name,'Expected an application filename')
        app=read(directory,app_name);version=m['version'];app_check(app,version,profile)
        ota_name=m.get('zigbee_file')
        require(m==full_manifest(app,version,config,app_name,ota_name),'Full manifest/hash/model mismatch')
        if config.get('full_ota'):
            require(isinstance(ota_name,str) and Path(ota_name).name==ota_name,'Expected an OTA filename')
            ota=read(directory,ota_name);inspect_ota(ota)
            require(ota==build_ota(app,file_version=version,**config['full_ota']),'Full OTA identity or payload mismatch')
            require(json_data(read(directory,'z2m-index.json'))==index(config['full_ota'],ota,version,ota_name),'Full index mismatch')
    except (KeyError,TypeError) as e:raise ValueError('Malformed full archive') from e
    return m


def load_base(directory,config,profile):
    directory=Path(directory)
    if (directory/'release-manifest.json').exists():
        metadata=verify_release(directory)
        require(metadata['name']==config['name'],'Base release name mismatch')
        folder=directory/'full'
    else:folder=directory
    m=verify_full(folder,config,profile)
    require(m['version']>=profile.min_base_version,'Base lacks delta support')
    return {'path':str(directory.resolve()),'app':str(inside(folder,m['app_file'])),
            'version':m['version'],'sha256':m['sha256'],'size':m['size']}


def check_bases(bases,version,config,profile):
    require(not bases or profile is not None,'Missing delta profile')
    result=[];versions=set()
    for directory in bases:
        base=load_base(directory,config,profile)
        require(base['version']<version,'Base version must precede the target')
        require(base['version'] not in versions,'Duplicate base version is ambiguous')
        versions.add(base['version']);result.append(base)
    return result


def create_deltas(root,image,version,bases,config,profile):
    from ota.delta_ota import make_delta
    checked=check_bases(bases,version,config,profile);result=[]
    for base in checked:
        name=f"deltas/from-{base['version']:08x}";directory=inside(root,name)
        make_delta(base['app'],image,base['version'],version,directory,profile)
        write(directory,'base.app.bin',Path(base['app']).read_bytes())
        result.append({'path':name,'base_version':base['version'],'base_sha256':base['sha256']})
    return result


def inventory(root):
    root=Path(root);result={}
    require(not root.is_symlink(),'Archive root symlink refused')
    for p in sorted(root.rglob('*')):
        require(not p.is_symlink(),'Archive contains a symlink')
        require(p.is_file() or p.is_dir(),'Unsupported archive entry')
        if not p.is_file() or p==root/'release-manifest.json':continue
        name=p.relative_to(root).as_posix();data=read(root,name)
        result[name]={'size':len(data),'sha256':digest(data)}
    return result


def finalize(root,metadata):
    require(not (Path(root)/'release-manifest.json').exists(),'Release already finalized')
    m=dict(metadata);m['files']=inventory(root);write(root,'release-manifest.json',encode(m))
    return m


def verify_release(root):
    root=Path(root)
    require(not root.is_symlink(),'Archive root symlink refused')
    m=json_data(read(root,'release-manifest.json',4*1024*1024))
    require(isinstance(m,dict) and type(m.get('schema_version')) is int and m['schema_version']==1 and m.get('kind')=='esp32-release','Invalid release manifest')
    try:
        config=release_config(encode(m['config']));require(m['name']==config['name'],'Release name mismatch')
        uint(m['version'],32,'release version')
        require(isinstance(m['files'],dict) and 1<=len(m['files'])<=4096,'Invalid file inventory')
        for name,item in m['files'].items():
            require(relative(name)==name and name!='release-manifest.json','Invalid inventory path')
            require(isinstance(item,dict) and set(item)=={'size','sha256'},'Invalid inventory entry')
            require(type(item['size']) is int and 0<=item['size']<=MAX_FILE,'Invalid artifact size')
            require(isinstance(item['sha256'],str) and len(item['sha256'])==64,'Invalid artifact digest')
        require(inventory(root)==m['files'],'Release files missing, added or changed')
        p=delta_profile(encode(m['delta_profile']),config['full_ota']) if m.get('delta_profile') is not None else None
        require(bool(p)==('delta_profile' in config),'Missing/extra release delta profile')
        full=verify_full(root/'full',config,p);require(full['version']==m['version'],'Release/full version mismatch')
        require(isinstance(m['deltas'],list),'Invalid delta inventory')
        versions=set()
        from ota.delta_ota import verify_delta
        for d in m['deltas']:
            require(isinstance(d,dict) and set(d)=={'path','base_version','base_sha256'},'Invalid delta entry')
            require(p is not None and type(d['base_version']) is int,'Missing delta profile/version')
            require(d['path']==f"deltas/from-{d['base_version']:08x}" and d['base_version'] not in versions,'Invalid/duplicate delta path')
            versions.add(d['base_version']);directory=inside(root,d['path'])
            checked=verify_delta(directory,directory/'base.app.bin',root/'full'/full['app_file'],p)
            require(checked['version']==m['version'] and checked['base_version']==d['base_version'] and checked['base_sha256']==d['base_sha256'],'Delta/source identity mismatch')
        expected={x.split('/')[1] for x in m['files'] if x.startswith('deltas/')}
        require(expected=={Path(d['path']).name for d in m['deltas']},'Unrepresented delta artifacts')
    except (KeyError,TypeError,IndexError) as e:raise ValueError('Malformed release archive') from e
    return m
