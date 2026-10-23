"""Run all speech-period contracts, including scripts with hyphenated names."""
import importlib.util
import sys
import unittest
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    suite = unittest.TestSuite()
    for path in sorted((root / 'tools').glob('test-*period*.py')):
        name = 'speech_'+path.stem.replace('-', '_')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    if suite.countTestCases() == 0:
        raise RuntimeError('No speech-quality tests found')
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(not result.wasSuccessful())


if __name__ == '__main__':
    main()
