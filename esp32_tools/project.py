"""Explicit project configuration and optional project-specific safety policy."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def require(ok, message):
    if not ok:
        raise ValueError(message)


def project_path(root, relative):
    require(isinstance(relative,str) and relative and not Path(relative).is_absolute(), 'Relative project path required')
    root=Path(root).resolve();result=(root/relative).resolve()
    require(result.is_relative_to(root), 'Path outside project refused')
    return result


def policy(root, config):
    if not config.get('policy'):
        return None
    path=project_path(root,config['policy'])
    name='_esp32_policy_'+hashlib.sha256(str(path).encode()).hexdigest()
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec)
        # Project policy may import its own adjacent helpers; common package uses qualified imports.
        sys.path.insert(0,str(path.parent))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        sys.modules[name]=module
    return sys.modules[name]


def load_config(root):
    root=Path(root).resolve()
    try:
        c=json.loads((root/'build-config.json').read_text())
        require(c['schema_version']==1,'Unsupported configuration schema')
        require(c['core']['id']=='esp32:esp32','ESP32 core required')
        require(re.fullmatch(r'\d+\.\d+\.\d+',c['core']['version']), 'Exact core version required')
        require(re.fullmatch(r'[A-Za-z0-9_-]+',c['board']['id']), 'Invalid board ID')
        require(isinstance(c['board']['options'],dict) and all(isinstance(k,str) and isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9_-]+',k) and re.fullmatch(r'[A-Za-z0-9_.-]+',v) for k,v in c['board']['options'].items()),'Invalid board options')
        require(c['board']['options'].get('PartitionScheme')=='custom','Custom partition scheme required')
        require(re.fullmatch(r'esp32[a-z0-9]*',c['chip']), 'Explicit ESP32 chip required')
        require(c['bootloader_offset'] in ('0x0','0x1000'), 'Explicit bootloader offset required')
        require(re.fullmatch(r'[A-Za-z_]\w*',c['version']['macro']), 'Invalid version macro')
        for name in ['sketch','partitions','version_header','requirements','build','firmware']:
            project_path(root,c['paths'][name])
        for relative in c['paths'].values():project_path(root,relative)
        sketch=project_path(root,c['paths']['sketch'])
        require(project_path(root,c['paths']['partitions'])==sketch/'partitions.csv','Partition CSV must be compiled sketch partitions.csv')
        require(type(c['upload_baud']) is int and 0<c['upload_baud']<=2000000,'Invalid upload baud')
        p=policy(root,c)
        if p is not None:p.validate_config(root,c)
        return c
    except (KeyError,TypeError,json.JSONDecodeError) as e:
        raise ValueError(f'Invalid build-config.json: {e}') from e


def fqbn(config):
    options=','.join(f'{k}={v}' for k,v in config['board']['options'].items())
    return f"{config['core']['id']}:{config['board']['id']}:"+options


def firmware_version(root,config):
    text=project_path(root,config['paths']['version_header']).read_text()
    matches=re.findall(r'^\s*#define\s+'+re.escape(config['version']['macro'])+r'\s+(0x[0-9a-fA-F]+|\d+)[uU]?\s*$',text,re.M)
    require(len(matches)==1,'Firmware version macro must be defined exactly once')
    n=int(matches[0],0);require(0<=n<=0xffffffff,'Firmware version outside uint32')
    return n,f'{n>>16}.{(n>>8)&255}.{n&255}'


def installed_cores():
    result=subprocess.run(['arduino-cli','core','list','--json'],capture_output=True,text=True,timeout=90)
    require(result.returncode==0,'Arduino core list failed')
    return json.loads(result.stdout)


def check_environment(root,config,core_list=None):
    from .partitions import layout_for
    cores=installed_cores() if core_list is None else core_list
    require(isinstance(cores,dict) and isinstance(cores.get('platforms'),list),'Invalid Arduino core response')
    versions=[x.get('installed_version') for x in cores['platforms'] if x.get('id')==config['core']['id']]
    require(versions==[config['core']['version']],f"Core {config['core']['version']} required; installed: {versions}")
    rows=layout_for(root,config,project_path(root,config['paths']['partitions']))
    lines=project_path(root,config['paths']['requirements']).read_text().splitlines()
    requirements=[x.strip() for x in lines if x.strip() and not x.lstrip().startswith('#')]
    require(requirements and all(re.fullmatch(r'.+?(==|>=|>|<=|<)\d+(?:\.\d+)*',x) for x in requirements),'Invalid library requirements')
    result=dict(version=firmware_version(root,config)[1],core=config['core']['version'],maximum_size=rows['app0'][3],zigbee_changed_files=[])
    p=policy(root,config)
    if p is not None:result.update(p.check_environment(root,config,cores))
    return result


def current():
    value=os.environ.get('ESP32_BUILD_PROJECT')
    require(value,'Use build.py --project PROJECT to select a project explicitly')
    root=Path(value).resolve()
    return root,load_config(root)
