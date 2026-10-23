#!/usr/bin/env python3
"""Example entry point; tools remain in the parent repository, no nested Git."""
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parent
TOOLS=ROOT.parents[1]
if not (TOOLS/'arduino/engine.py').is_file():
    raise SystemExit('Use this example inside esp32-firmware-tools, or adapt TOOLS to your pinned tools submodule.')
raise SystemExit(subprocess.call([sys.executable,str(TOOLS/'build.py'),'--project',str(ROOT),*sys.argv[1:]],cwd=ROOT))
