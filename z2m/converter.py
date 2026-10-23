#!/usr/bin/env python3
"""Validate a firmware capability descriptor and generate an ESM Z2M converter."""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile
import os

if not __package__:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common.console import safe_print as print

MAX_BYTES=65536
CLUSTERS={'on_off':6,'binary_input':15,'temperature':1026,'humidity':1029}


def require(ok,message):
    if not ok:raise ValueError(message)


def fields(value,allowed,required,label):
    require(isinstance(value,dict),label+' must be an object')
    require(set(value)<=set(allowed) and set(required)<=set(value),label+' has unknown or missing fields')


def integer(value,minimum,maximum,label):
    require(type(value) is int and minimum<=value<=maximum,label+' outside supported range')
    return value


def text(value,maximum,label,identifier=False):
    require(isinstance(value,str) and 0<len(value.encode('utf-8'))<=maximum,label+' must be nonempty text within the byte limit')
    if identifier:require(re.fullmatch(r'[a-z][a-z0-9_]{0,31}',value),label+' must be a lowercase property identifier')
    else:require(all(ord(c)>=32 and ord(c)!=127 for c in value),label+' contains control characters')
    return value


def validate(value):
    fields(value,['schema_version','device','endpoints','ota'],['schema_version','device','endpoints','ota'],'descriptor')
    require(type(value['schema_version']) is int and value['schema_version']==1,'Unsupported descriptor schema')
    d=value['device'];fields(d,['model','manufacturer','description','firmware_version'],['model','manufacturer','description'],'device')
    device={k:text(d[k],32 if k!='description' else 512,'device.'+k) for k in ['model','manufacturer','description']}
    if 'firmware_version' in d:
        v=d['firmware_version']
        device['firmware_version']=integer(v,0,0xffffffff,'firmware_version') if type(v) is int else text(v,64,'firmware_version')
    require(type(value['ota']) is bool,'ota must be boolean')
    require(isinstance(value['endpoints'],list) and 1<=len(value['endpoints'])<=32,'Expected 1 to 32 endpoints')
    endpoints=[];ids=set();names=set()
    for ep in value['endpoints']:
        fields(ep,['id','name','clusters','features'],['id','name','clusters','features'],'endpoint')
        number=integer(ep['id'],1,240,'endpoint id');name=text(ep['name'],32,'endpoint name',True)
        require(number not in ids and name not in names,'Duplicate endpoint id or name');ids.add(number);names.add(name)
        fields(ep['clusters'],['input','output'],['input','output'],'clusters');clusters={}
        for direction in ['input','output']:
            seq=ep['clusters'][direction];require(isinstance(seq,list) and len(seq)<=64,'Invalid cluster list')
            for n in seq:integer(n,0,0xffff,'cluster id')
            require(len(seq)==len(set(seq)),'Duplicate cluster id');clusters[direction]=sorted(seq)
        require(isinstance(ep['features'],list) and 1<=len(ep['features'])<=4,'Expected 1 to 4 standard features')
        features=[];types=set()
        for f in ep['features']:
            fields(f,['type','property','reporting'],['type'],'feature');kind=f['type']
            require(isinstance(kind,str) and kind in CLUSTERS,'Unsupported feature type')
            require(kind not in types,'Duplicate feature type');types.add(kind)
            require(CLUSTERS[kind] in clusters['input'],'Feature requires its server/input cluster')
            item={'type':kind}
            if kind=='binary_input':item['property']=text(f.get('property','state'),32,'binary property',True)
            else:require('property' not in f,'Property override is supported only for binary_input')
            if 'reporting' in f:
                require(kind!='on_off','on_off uses standard Z2M reporting')
                r=f['reporting'];fields(r,['min','max','change'],['min','max','change'],'reporting')
                lo=integer(r['min'],0,65534,'reporting min');hi=integer(r['max'],1,65534,'reporting max')
                require(lo<=hi,'Reporting min exceeds max')
                change=integer(r['change'],0,1 if kind=='binary_input' else 32767,'reporting change')
                item['reporting']={'min':lo,'max':hi,'change':change}
            features.append(item)
        described={CLUSTERS[k] for k in types}
        require(set(clusters['input']) <= {0,3,4,5}|described,'Unrepresented or unsupported server cluster')
        endpoints.append({'id':number,'name':name,'clusters':clusters,'features':sorted(features,key=lambda x:x['type'])})
    if value['ota']:require(any(25 in ep['clusters']['output'] for ep in endpoints),'OTA advertised without an OTA client cluster')
    return {'schema_version':1,'device':device,'ota':value['ota'],'endpoints':sorted(endpoints,key=lambda x:x['id'])}


def no_duplicates(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON key');result[key]=value
    return result


def parse_descriptor(data):
    require(len(data)<=MAX_BYTES,'Descriptor exceeds 64 KiB')
    try:value=json.loads(data.decode('utf-8'),object_pairs_hook=no_duplicates)
    except (UnicodeError,json.JSONDecodeError) as e:raise ValueError('Invalid UTF-8 descriptor JSON') from e
    return validate(value)


def load_descriptor(path):
    with Path(path).open('rb') as f:return parse_descriptor(f.read(MAX_BYTES+1))


def generate(value):
    d=validate(value);device=d['device'];mapping={ep['name']:ep['id'] for ep in d['endpoints']}
    j=lambda value:json.dumps(value,ensure_ascii=True)
    extends=['m.deviceEndpoints('+j({'endpoints':mapping})+')']
    for ep in d['endpoints']:
        for f in ep['features']:
            kind=f['type'];name=ep['name']
            if kind=='on_off':
                options={'endpointNames':[name],'powerOnBehavior':False,'configureReporting':True};method='onOff'
            elif kind=='binary_input':
                options={'name':f['property'],'cluster':'genBinaryInput','attribute':'presentValue','valueOn':[True,1],'valueOff':[False,0],'access':'STATE_GET','endpointName':name,'reporting':f.get('reporting',{'min':0,'max':60,'change':1})};method='binary'
            else:
                options={'endpointNames':[name],'reporting':f.get('reporting',{'min':5,'max':60,'change':10 if kind=='temperature' else 100})};method=kind
            extends.append('m.'+method+'('+j(options)+')')
    return ('// Generated from firmware capabilities; edit the firmware descriptor.\n'
        "import * as m from 'zigbee-herdsman-converters/lib/modernExtend';\n\n"
        'export default {\n    fingerprint: '+j([{'modelID':device['model'],'manufacturerName':device['manufacturer']}])+',\n'
        '    model: '+j(device['model'])+',\n    vendor: '+j(device['manufacturer'])+',\n'
        '    description: '+j(device['description'])+',\n    ota: '+j(d['ota'])+',\n'
        '    extend: [\n        '+',\n        '.join(extends)+'\n    ],\n};\n')


def write_output(path,content,force=False,source=None):
    path=Path(path)
    require(not path.is_symlink(),'Output symlinks are refused')
    if source is not None:require(path.resolve()!=Path(source).resolve(),'Input and output must be different')
    path.parent.mkdir(parents=True,exist_ok=True)
    if not force:
        with path.open('x',encoding='utf-8',newline='\n') as f:f.write(content)
    else:
        name=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='\n',dir=path.parent,delete=False) as f:
                name=f.name;f.write(content)
            os.replace(name,path);name=None
        finally:
            if name is not None:Path(name).unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('generate');p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--force',action='store_true')
    p=sub.add_parser('validate');p.add_argument('--input',type=Path,required=True)
    args=parser.parse_args()
    try:
        d=load_descriptor(args.input)
        if args.command=='generate':write_output(args.output,generate(d),args.force,args.input);print('Generated:',args.output)
        else:print('Descriptor valid:',d['device']['model'],';',len(d['endpoints']),'endpoints')
    except (OSError,ValueError,TypeError) as e:parser.exit(1,f'Refused: {e}\n')

if __name__=='__main__':main()
