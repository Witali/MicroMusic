"""Sibling-import bootstrap for a runtime that executes scripts with runpy."""
from pathlib import Path
import runpy
import sys

here = Path(__file__).resolve().parent
sys.path.insert(0,str(here))
sys.argv[0] = str(here/'replay.py')
runpy.run_path(str(here/'replay.py'),run_name='__main__')
