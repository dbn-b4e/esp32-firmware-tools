#!/usr/bin/env python3
"""Shared CLI; project firmware keeps a small build.py forwarding here."""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--project',required=True,type=Path,help='Racine du projet firmware contenant build-config.json')
    raw=sys.argv[1:]
    if any(a in ('-h','--help') for a in raw) and not any(a=='--project' or a.startswith('--project=') for a in raw):
        parser.print_help()
        print('Backend actuel : Arduino CLI. Ajouter --project CHEMIN --help pour ses options.')
        print('OTA autonome : python3 ota/zigbee_ota_generator.py --help ; python3 ota/delta_ota.py --help')
        return 0
    args,rest=parser.parse_known_args()
    os.environ['ESP32_BUILD_PROJECT']=str(args.project.resolve())
    sys.argv=[sys.argv[0],*rest]
    try:
        from arduino.project import current, project_path
        root, config = current()
        os.chdir(project_path(root, config['paths']['sketch']))
        from arduino.engine import main as engine
        return engine()
    except (ValueError,OSError,KeyError) as exc:
        print(f'Build refused: {exc}',file=sys.stderr)
        return 2

if __name__=='__main__':sys.exit(main())
