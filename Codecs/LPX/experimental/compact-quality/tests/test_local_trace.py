"""Independent canonical/native LPC-crop regression, standard Python only.

The implementation is included once by the test TU to reach a private helper;
no new production API/test seam or production compilation unit is added.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
ACTIVE = REPO / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, help='Alternate original LpxLpcRefine.cpp for before/after proof')
parser.add_argument('--expect-pre-fix', action='store_true', help='Require regression exit30 in P3 and continuation; controls still must pass')
OPTIONS, remaining = parser.parse_known_args()
OUTPUT = REPO / ('build/compact-quality/independent-pre-fix' if OPTIONS.expect_pre_fix else 'build/compact-quality/independent-fixed')


def native(path):
    path = Path(path).resolve()
    if os.name == 'nt' and os.environ.get('LPX_TEST_WSL'):
        return '/mnt/' + path.drive[0].lower() + '/' + '/'.join(path.parts[1:])
    return str(path)


class LocalTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prefix = ['wsl', '-d', os.environ['LPX_TEST_WSL'], '--'] if os.name == 'nt' and os.environ.get('LPX_TEST_WSL') else []
        OUTPUT.mkdir(parents=True, exist_ok=True)
        implementation = (OPTIONS.source or ACTIVE / 'host/LpxLpcRefine.cpp').resolve()
        config = (REPO / 'web-player/scripts/lib/lpx-build.mjs').read_text(encoding='utf-8')
        names = re.findall(r"'([^']+\.cpp)'", config.split('export const hostSources=host([')[1].split(']);')[0])
        defines = re.findall(r"'([^']+)'", config.split('export const portableDefines=[')[1].split('];')[0])
        sources = [ACTIVE / 'src/Lpx4HybridCore.cpp', ACTIVE / 'host/LpxEncoder.cpp',
                   *(ACTIVE / 'host' / name for name in names if name != 'LpxLpcRefine.cpp'), HERE / 'local_trace.cpp']
        inputs = [*sources, implementation, *(ACTIVE / 'host').glob('*.h'), *(ACTIVE / 'src').glob('*.h'),
                  *(ACTIVE / 'host').glob('*.inc'), *(ACTIVE / 'src').glob('*.inc')]
        before = {str(p.relative_to(REPO).as_posix()): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        command = ['g++', '-O2', '-std=c++11', '-ffp-contract=off', *('-D' + d for d in defines),
                   '-DLPX_LPC_REFINE_SOURCE="' + native(implementation) + '"',
                   '-include', native(ACTIVE / 'host/LpxHostWorkspace.h'),
                   '-I' + native(ACTIVE / 'src'), '-I' + native(ACTIVE / 'host'),
                   *(native(p) for p in sources), '-o', native(OUTPUT / 'local-trace-tests')]
        done = subprocess.run(cls.prefix + command, capture_output=True, text=True)
        if done.returncode:
            raise AssertionError(done.stdout + done.stderr)
        if before != {str(p.relative_to(REPO).as_posix()): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}:
            raise RuntimeError('Inputs changed during the independent build')
        cls.receipt = dict(compiler=subprocess.check_output(cls.prefix + ['g++', '--version'], text=True).splitlines()[0],
                           command=command, sources=before, expect_pre_fix=OPTIONS.expect_pre_fix, results={})

    @classmethod
    def tearDownClass(cls):
        (OUTPUT / 'receipt.json').write_text(json.dumps(cls.receipt, indent=2) + '\n', encoding='utf-8')

    def check(self, mode):
        done = subprocess.run(self.prefix + [native(OUTPUT / 'local-trace-tests'), mode], capture_output=True, text=True)
        expected = 30 if OPTIONS.expect_pre_fix and mode in ('trace', 'continuation') else 0
        self.receipt['results'][mode] = dict(returncode=done.returncode, stdout=done.stdout.strip(), stderr=done.stderr.strip())
        self.assertEqual(done.returncode, expected, done.stdout + done.stderr)
        self.assertIn('REGRESSION' if expected else 'PASS', done.stdout)

    def test_p3_coefficients_and_native_forward_audio(self): self.check('trace')
    def test_p4_p6_p8_unchanged_trace_contract(self): self.check('controls')
    def test_real_assembled_prefix_suffix_continuation(self): self.check('continuation')
    def test_proposal_noops_bounds_determinism_and_metadata(self): self.check('proposals')


if __name__ == '__main__':
    unittest.main(argv=[__file__, *remaining], verbosity=2)
