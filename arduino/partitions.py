"""Partition guards; project policy can add stricter constraints."""
import csv
from pathlib import Path
import re
import struct
import subprocess
from .project import require,policy,current


def parse_layout(path,flash_size):
    rows={};end=0x9000
    for row in csv.reader(Path(path).read_text().splitlines()):
        if not row or row[0].strip().startswith('#'):continue
        require(len(row)>=5,'Invalid partition row')
        name,kind,subtype,offset,size=(x.strip() for x in row[:5])
        offset,size=int(offset,0),int(size,0)
        require(name not in rows and size>0 and offset>=end and offset+size<=flash_size,'Invalid/overlapping/oversized partition: '+name)
        require(offset%4096==size%4096==0 and (kind!='app' or offset%65536==0),'Unaligned partition: '+name)
        rows[name]=(kind,subtype,offset,size);end=offset+size
    require('app0' in rows and rows['app0'][:2]==('app','ota_0'),'Application partition app0/ota_0 required')
    require(rows.get('otadata', ())[:2] == ('data', 'ota') and rows['otadata'][3] >= 0x2000,
            'OTA boot metadata requires a data/ota partition of at least 8 KiB')
    if 'littlefs' in rows:
        require(rows['littlefs'][:2] == ('data', 'spiffs'), 'LittleFS must be a data/spiffs partition')
    return rows


def flash_size(config):
    value=config['board']['options'].get('FlashSize','')
    require(re.fullmatch(r'\d+M',value),'FlashSize must specify MiB, e.g. 4M')
    return int(value[:-1])*1024*1024


def layout_for(root,config,path):
    rows=parse_layout(path,flash_size(config))
    p=policy(root,config)
    if p is not None:p.validate_layout(path)
    return rows


def validate_layout(path):
    root,config=current();return layout_for(root,config,path)


def decode_table(data):
    result={}
    for i in range(0,len(data)-31,32):
        magic,kind,subtype,offset,size,label,flags=struct.unpack('<HBBII16sI',data[i:i+32])
        if magic!=0x50aa:break
        label=label.split(b'\0',1)[0].decode('ascii')
        require(label not in result,'Duplicate partition label')
        result[label]=(kind,subtype,offset,size)
    require(result,'Invalid device partition table');return result


def check_table_rows(rows,binary):
    """Validate a compiled table against explicit rows, without global project state."""
    subtypes={'nvs':2,'ota':0,'fat':0x81,'spiffs':0x82,'coredump':3,**{f'ota_{i}':0x10+i for i in range(16)}}
    expected={name:(0 if row[0]=='app' else 1,subtypes[row[1]],row[2],row[3]) for name,row in rows.items()}
    require(decode_table(binary)==expected,'Device partition table differs; explicit USB migration required')


def check_table_matches(csv_path,binary):
    check_table_rows(validate_layout(csv_path),binary)


def validate_device(esptool_command,port,csv_path,workdir,check_partition=False):
    root,config=current();p=policy(root,config)
    if p is not None:
        return p.validate_device(esptool_command,port,csv_path,workdir,check_partition)
    require(port,'Explicit device port required')
    workdir=Path(workdir);workdir.mkdir(parents=True,exist_ok=True)
    base=[*esptool_command,'--chip',config['chip'],'--port',port]
    r=subprocess.run([*base,'flash-id'],capture_output=True,text=True,timeout=30)
    expected=f"Detected flash size: {flash_size(config)//(1024*1024)}MB"
    require(r.returncode==0 and expected in r.stdout,'Device chip/flash size does not match project')
    if check_partition:
        table=workdir/'device-partitions.bin'
        subprocess.run([*base,'read-flash','0x8000','0x1000',str(table)],check=True,timeout=30)
        data=table.read_bytes()
        if data.strip(b'\xff'):check_table_matches(csv_path,data)  # blank flash = new device
