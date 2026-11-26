"""Synthetic P3 temporal policy regression; no audio corpus is required."""
import os
from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
ACTIVE = HERE.parent
ROOT = ACTIVE.parents[2]


def native(path):
    path = Path(path).resolve()
    if os.name == 'nt' and os.environ.get('LPX_TEST_WSL'):
        return '/mnt/' + path.drive[0].lower() + '/' + '/'.join(path.parts[1:])
    return str(path)


class TemporalPolicyTests(unittest.TestCase):
    def test_default_and_explicit_legacy(self):
        prefix = ['wsl', '-d', os.environ['LPX_TEST_WSL'], '--'] if os.name == 'nt' and os.environ.get('LPX_TEST_WSL') else []
        output = ROOT / 'build/intelligibility/temporal-tests'
        output.mkdir(parents=True, exist_ok=True)
        for mode in (0, 2):
            with self.subTest(deadzone=mode):
                binary = output / ('policy-' + str(mode))
                flags = [] if mode == 0 else ['-DLPX_ENCODER_P3_TEMPORAL_DEADZONE=2']
                built = subprocess.run(prefix + ['g++', '-O2', '-std=c++11', *flags,
                    '-I' + native(ACTIVE / 'host'), native(HERE / 'p3_temporal.cpp'),
                    '-o', native(binary)], capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
                checked = subprocess.run(prefix + [native(binary)], capture_output=True, text=True)
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
                self.assertIn('PASS:', checked.stdout)
                print(checked.stdout.strip())


if __name__ == '__main__':
    unittest.main(verbosity=2)
