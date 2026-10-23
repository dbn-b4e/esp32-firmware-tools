"""Release subcommands behind the shared build.py entry point."""
import argparse,json,subprocess
from pathlib import Path
from common.console import safe_print as print
from .source import make_plan
from .config import delta_profile
from . import archive


def main(project,args):
    p=argparse.ArgumentParser(prog='build.py release',description='Build an exact local Git tag and verify immutable full/delta archives; no deployment.')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ['plan','build']:
        q=sub.add_parser(name);q.add_argument('--ref',required=True,help='Existing local Git tag, not a branch')
        q.add_argument('--base-release',type=Path,action='append',default=[],help='Exact archived base; repeat for several bases')
        q.add_argument('--output',help='New project-relative Git-ignored destination')
    q=sub.add_parser('verify');q.add_argument('--archive',type=Path,required=True)
    a=p.parse_args(args)
    try:
        if a.command=='verify':
            root=a.archive if a.archive.is_absolute() else Path(project or '.').resolve()/a.archive
            m=archive.verify_release(root);print(json.dumps({'verified':str(root),'version':m['version'],'deltas':len(m['deltas'])}));return 0
        if project is None:p.error('--project is required for plan/build')
        plan=make_plan(project,a.ref,a.output,a.base_release)
        profile=delta_profile(archive.encode(plan['delta_profile']),plan['config']['full_ota']) if plan['delta_profile'] else None
        archive.check_bases(plan['bases'],plan['version'],plan['config'],profile)
        if a.command=='plan':print(json.dumps(plan,indent=2,ensure_ascii=True));return 0
        from .runner import build_release
        print('Building tag',plan['source']['tag'],'at',plan['source']['commit'],flush=True)
        result=build_release(plan);print('Verified release:',result);return 0
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as e:
        p.exit(1,'Release refused: '+str(e)+'\n')
