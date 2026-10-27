"""Run the existing Arduino backend on an isolated source export; never flash."""
from datetime import datetime,timezone
import hashlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path
from . import source,archive
from .config import inside,delta_profile
from ota.zigbee_ota_generator import require

TOOLS=Path(__file__).resolve().parents[1]


def tool_identity():
    files=[TOOLS/'build.py',TOOLS/'requirements.txt',TOOLS/'requirements-delta.txt']
    for folder in ['arduino','common','ota','release_tools']:files.extend((TOOLS/folder).rglob('*.py'))
    records={p.relative_to(TOOLS).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    commit=source.git(TOOLS,'rev-parse','HEAD',check=False).stdout.decode().strip()
    return {'commit':commit or None,'code_sha256':hashlib.sha256(archive.encode(records)).hexdigest(),'files':records}


def parse_libraries(text):
    if 'USED LIBRARIES' not in text:return []
    section=re.split(r'\n(?:LIBRARY VALIDATION|PLATFORM)\s*\n',text.split('USED LIBRARIES',1)[1],maxsplit=1)[0]
    return [{'name':name.strip(),'version':version} for name,version in re.findall(r'^\s*•\s+(.+?)\s+v(\S+)\s+',section,re.M)]


def run_backend(project,log):
    log=Path(log)
    with log.open('w',encoding='utf-8') as output:
        log.chmod(0o600)
        command=[sys.executable,str(TOOLS/'build.py'),'--project',str(project),'--build','--silent']
        result=subprocess.run(command,stdout=output,stderr=subprocess.STDOUT,cwd=project,timeout=1800)
    require(result.returncode==0,'Backend failed; private diagnostics: '+str(log))
    config=json.loads((project/'build-config.json').read_text())
    report=inside(project,config['paths']['sketch'])/'info/build_log.txt'
    libraries=[]
    if report.is_file():
        libraries=parse_libraries(report.read_text())
    cli=subprocess.run(['arduino-cli','version','--format','json'],capture_output=True,text=True,timeout=15)
    require(cli.returncode==0,'Cannot record Arduino CLI version')
    try:cli_info=json.loads(cli.stdout)
    except json.JSONDecodeError:cli_info={'reported_version':cli.stdout.strip()}
    return {'libraries':libraries,'arduino_cli':cli_info}


def check_tool_pin(plan,allow_mismatch=False):
    """The tag pins the engine that built it; packaging with another engine must be explicit."""
    if allow_mismatch:return
    mine=tool_identity()['commit']
    for m in plan['source']['submodules']:
        r=source.git(m['repository'],'ls-tree','--name-only',m['commit'],'--','release_tools/cli.py',check=False)
        if r.returncode==0 and r.stdout.strip():
            require(mine==m['commit'],'Tagged tools submodule '+m['commit'][:12]+' differs from the running engine '
                    +((mine or 'unknown')[:12])+'; check out the pinned tools or pass --allow-tool-mismatch')


def build_release(plan,allow_tool_mismatch=False):
    check_tool_pin(plan,allow_tool_mismatch)
    project=Path(plan['project_root']);destination=Path(plan['output'])
    require(inside(project,destination.relative_to(project).as_posix())==destination,'Invalid output destination')
    require(source.ignored(Path(plan['source']['repository']),destination),'Output must be ignored')
    require(not destination.exists(),'Release output already exists')
    profile=delta_profile(archive.encode(plan['delta_profile']),plan['config']['full_ota']) if plan['delta_profile'] else None
    legacy=delta_profile(archive.encode(plan['legacy_base_profile']),plan['config']['full_ota']) if plan.get('legacy_base_profile') else None
    checked_bases=archive.check_bases(plan['bases'],plan['version'],plan['config'],profile,legacy)
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    destination.mkdir(mode=0o700);archive.write(destination,'.incomplete',b'Build in progress; not a validated release.\n')
    workbase=inside(project,'build/release-work');workbase.mkdir(parents=True,exist_ok=True,mode=0o700);workbase.chmod(0o700)
    workspace=Path(tempfile.mkdtemp(prefix='tag-',dir=workbase));log=workspace/'build.log'
    identity=tool_identity()
    try:
        selected=source.materialize(plan,workspace/'source')
        firmware=inside(selected,plan['build_config']['paths']['firmware'])
        require(not firmware.exists() or not list(firmware.rglob('*.bin')),'Tagged source contains prebuilt firmware outputs')
        critical={'build-config.json','release-config.json',*(plan['build_config']['paths'][k] for k in ['version_header','partitions','requirements'])}
        if 'delta_profile' in plan['config']:critical.add(plan['config']['delta_profile'])
        selected_hashes={name:archive.digest(inside(selected,name).read_bytes()) for name in critical}
        build_info=run_backend(selected,log)
        require(all(archive.digest(inside(selected,name).read_bytes())==value for name,value in selected_hashes.items()),'Selected input changed during the build')
        require(tool_identity()['code_sha256']==identity['code_sha256'],'Tool source changed during the build')
        require(archive.check_bases(plan['bases'],plan['version'],plan['config'],profile,legacy)==checked_bases,'Base archive changed during the build')
        # Input files must still describe what was copied into this exact source export.
        for item in plan['local_inputs']:
            data=inside(selected,item['path']).read_bytes()
            require(len(data)==item['size'] and archive.digest(data)==item['sha256'],'Local input changed during the build')
        require(json.loads((selected/'build-config.json').read_text())==plan['build_config'],'Build configuration changed during the build')
        sketch=inside(selected,plan['build_config']['paths']['sketch']);inos=list(sketch.glob('*.ino'))
        require(len(inos)==1,'Exactly one compiled sketch required')
        app=inside(firmware,inos[0].name+'.bin');require(app.is_file(),'Backend did not produce the application binary')
        from arduino.partitions import parse_layout,flash_size
        rows=parse_layout(inside(selected,plan['build_config']['paths']['partitions']),flash_size(plan['build_config']))
        require(app.stat().st_size<=rows['app0'][3],'Application exceeds the actual partition')
        full=archive.create_full(destination/'full',app,plan['version'],plan['config'],profile)
        deltas=archive.create_deltas(destination,app,plan['version'],plan['bases'],plan['config'],profile,legacy)
        for p in sorted(firmware.glob('*.bin')):
            if p==app:continue
            archive.write(destination,'components/'+p.name,p.read_bytes())
        archive.write(destination,'build/build.log',log.read_bytes())
        report=sketch/'info/build_log.txt'
        if report.is_file():archive.write(destination,'build/arduino-report.txt',report.read_bytes())
        archive.write(destination,'build/build-config.json',(selected/'build-config.json').read_bytes())
        archive.write(destination,'build/partitions.csv',inside(selected,plan['build_config']['paths']['partitions']).read_bytes())
        archive.write(destination,'build/requirements.txt',inside(selected,plan['build_config']['paths']['requirements']).read_bytes())
        metadata={'schema_version':1,'kind':'esp32-release','name':plan['config']['name'],'version':plan['version'],
            'version_text':plan['version_text'],'created_utc':datetime.now(timezone.utc).isoformat(),
            'source':{k:v for k,v in plan['source'].items() if k not in ['repository','submodules']},
            'config':plan['config'],'delta_profile':plan['delta_profile'],'legacy_base_profile':plan.get('legacy_base_profile'),'local_inputs':plan['local_inputs'],
            'build':{'core':plan['build_config']['core'],'board':plan['build_config']['board'],'chip':plan['build_config']['chip'],**build_info},
            'tools':identity,'deltas':deltas,'components':{'sketch':inos[0].name,'filesystem_required':(sketch/'data').is_dir()}}
        metadata['source']['submodules']=[{k:v for k,v in m.items() if k!='repository'} for m in plan['source']['submodules']]
        archive.verify_components(destination,metadata['components'],full)
        (destination/'.incomplete').unlink()
        archive.finalize(destination,metadata);archive.verify_release(destination)
    except BaseException:
        if log.exists():log.chmod(0o600)
        # Never leave a failed package carrying the completion marker.
        manifest=destination/'release-manifest.json'
        if manifest.exists():manifest.unlink()
        if not (destination/'.incomplete').exists():archive.write(destination,'.incomplete',b'Build or verification failed.\n')
        raise
    return destination
