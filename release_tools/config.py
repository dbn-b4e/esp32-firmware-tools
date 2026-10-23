"""Strict release configuration: public metadata and declared local input paths."""
import json
from pathlib import Path,PurePosixPath
import re
from ota.zigbee_ota_generator import build_ota,require


def relative(value):
    require(isinstance(value,str) and value and '\\' not in value and ':' not in value,'Expected a relative portable path')
    p=PurePosixPath(value)
    require(not p.is_absolute() and all(x not in ('..','.git') for x in p.parts) and p.parts,'Path escapes the project')
    return p.as_posix()


def inside(root,name):
    root=Path(root).resolve();name=relative(name);p=root/name
    require(p.resolve().is_relative_to(root),'Path escapes the project')
    for part in [p,*p.parents]:
        if part==root:break
        require(not part.is_symlink(),'Path contains a symlink')
    return p


def _pairs(items):
    d={}
    for k,v in items:
        require(k not in d,'Duplicate JSON key');d[k]=v
    return d


def json_data(raw):
    try:return json.loads(raw,object_pairs_hook=_pairs)
    except (UnicodeError,json.JSONDecodeError) as e:raise ValueError('Invalid release JSON') from e


def release_config(raw):
    d=json_data(raw)
    require(isinstance(d,dict) and set(d)<={'schema_version','name','local_inputs','full_ota','delta_profile'},'Unknown release-config field')
    require(type(d.get('schema_version')) is int and d['schema_version']==1,'Unsupported release-config schema')
    require(isinstance(d.get('name'),str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',d['name']),'Invalid release name')
    require(isinstance(d.get('local_inputs',[]),list),'Invalid local_inputs')
    d['local_inputs']=[relative(p) for p in d.get('local_inputs',[])]
    require(len(set(d['local_inputs']))==len(d['local_inputs']),'Duplicate local input')
    if 'full_ota' in d:
        full=d['full_ota']
        required={'manufacturer_code','image_type','header_string','stack_version','min_hardware_version','max_hardware_version','espressif_compatible'}
        require(isinstance(full,dict) and set(full)==required,'Explicit full_ota fields required')
        require(type(full['espressif_compatible']) is bool,'Invalid padding option')
        build_ota(b'x',file_version=0,**full)
    if 'delta_profile' in d:
        d['delta_profile']=relative(d['delta_profile'])
        require('full_ota' in d,'Delta needs the full fallback configuration')
    return d


def delta_profile(raw,full):
    from ota.delta_ota import DeltaProfile
    d=json_data(raw)
    require(isinstance(d,dict),'Invalid delta profile')
    try:
        d['envelope_magic']=bytes.fromhex(d.pop('magic_hex'));p=DeltaProfile(**d)
    except (KeyError,TypeError,ValueError) as e:raise ValueError('Invalid delta profile') from e
    for field in ['manufacturer_code','image_type','stack_version','min_hardware_version','max_hardware_version']:
        require(full[field]==getattr(p,field),'Full/delta OTA identity mismatch: '+field)
    require(full['header_string']==p.model and full['espressif_compatible'],'Full/delta model or padding mismatch')
    return p
