"""Resolve tools from Arduino's selected build properties, not OS-specific guesses."""
from functools import lru_cache
import os
from pathlib import Path
import subprocess
from .project import current,fqbn,project_path,require


def parse_properties(text):
    return dict(line.split('=',1) for line in text.splitlines() if '=' in line)


@lru_cache(maxsize=1)
def build_properties():
    root,c=current();work=project_path(root,c['paths']['build'])/'tool-properties'
    work.mkdir(parents=True,exist_ok=True)
    cmd=['arduino-cli','compile','--fqbn',fqbn(c),'--build-path',str(work),'--show-properties',str(project_path(root,c['paths']['sketch']))]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    require(result.returncode==0,'Cannot read selected Arduino build properties: '+result.stderr[-1000:])
    properties=parse_properties(result.stdout)
    require(Path(properties.get('runtime.platform.path','')).name==c['core']['version'],'Selected platform does not match pinned core')
    return properties


def resolve_tool(properties,name,system=None):
    folder=properties.get(f'runtime.tools.{name}.path')
    require(folder,f'Arduino did not select tool {name}')
    folder=Path(folder);binary='esptool' if name=='esptool_py' else name
    candidates=[binary+'.exe',binary+'.py'] if (system or os.name)=='nt' else [binary,binary+'.py']
    for candidate in candidates:
        path=folder/candidate
        if path.is_file():return path
    raise ValueError(f'Missing selected tool {name} in {folder}')


def boot_app0(properties,version):
    platform=Path(properties['runtime.platform.path'])
    require(platform.name==version,'Boot metadata must come from selected core version')
    result=platform/'tools/partitions/boot_app0.bin'
    require(result.is_file(),'Missing boot_app0.bin in selected platform')
    return result


def selected_tool(name):
    return str(resolve_tool(build_properties(),name))


def selected_boot_app0():
    _,c=current()
    return str(boot_app0(build_properties(),c['core']['version']))
