"""Run the focused checks for the saved encoder research checkpoint.

Requires the project Python dependencies and a native C++ compiler. Generated
native libraries and synthetic streams remain under ignored build storage.
This does not execute corpus fitting, AVR simulation or the pending chain audit.
"""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[5]
ACTIVE = ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
MODULES = [
    'test_speech_objective', 'test_speech_rate_allocation',
    'test_refine_speech_lpc', 'test_perceptual_rate',
    'test_enhance_speech_compact', 'test_refine_speech_trajectory',
    'test_speech_chain_frontier', 'test_run_v5_encoder_study',
    'test_refine_speech_perceptual', 'test_speech_parameter_histograms',
    'test_nonspeech_trajectory', 'test_speech_parameter_costs',
    'test_cleanup_speech_compact',
]
FILES = [
    ('checkpoint_combined_protocol', 'v5-combined-study-2026-10-28/reproduction/test_protocol.py'),
    ('checkpoint_scale_repeat', 'v6-scale-repeat-2026-10-28/prototype/test_scale_repeat.py'),
]


def main():
    sys.path[:0] = [str(ACTIVE / 'tools'), str(ACTIVE / 'tests')]
    loader = unittest.defaultTestLoader
    suite = loader.loadTestsFromNames(MODULES)
    for alias, relative in FILES:
        path = ROOT / 'Codecs/LPX/research' / relative
        spec = importlib.util.spec_from_file_location(alias, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(loader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    receipt = dict(tests_run=result.testsRun, failures=len(result.failures),
                   errors=len(result.errors), skipped=len(result.skipped),
                   successful=result.wasSuccessful())
    output = ROOT / 'build/encoder-quality/checkpoint-tests.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt))
    return not result.wasSuccessful()


if __name__ == '__main__':
    raise SystemExit(main())
