"""Run the isolated host research prototype with existing LPX dependencies."""
from pathlib import Path
import runpy
import sys
import unittest

STUDY = Path(__file__).resolve().parent
REPOSITORY = STUDY.parents[3]
ACTIVE = REPOSITORY / "Codecs/LPX/01_ACTIVE_Q0_CODEC"
sys.path[:0] = [str(STUDY / "prototype"), str(STUDY / "tests"),
                str(ACTIVE / "tools"), str(ACTIVE / "tests")]
if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("test", "benchmark"):
        raise SystemExit("Usage: run.py test | benchmark MANIFEST OUTPUT [options]")
    action = sys.argv.pop(1)
    if action == "test":
        suite = unittest.defaultTestLoader.discover(str(STUDY / "tests"))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(not result.wasSuccessful())
    runpy.run_path(str(STUDY / "prototype/benchmark_period_excitation.py"), run_name="__main__")
