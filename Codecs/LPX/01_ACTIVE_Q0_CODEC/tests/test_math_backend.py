"""The portable backend remains selectable and agrees with independent math."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MathBackendTests(unittest.TestCase):
    def build_run(self, flags):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)/'math.exe'
            subprocess.run(['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),*flags,
                str(ROOT/'tests/math_backend.cpp'),'-o',str(output)], check=True, capture_output=True)
            result = json.loads(subprocess.check_output([str(output)],text=True))
        self.assertEqual(result['cases'], 4946305)
        self.assertEqual(result['error'], 0)
        self.assertEqual(result['backend'], 0)

    def test_default_portable_math_full_range(self):
        self.build_run([])

    def test_asm_opt_in_on_unsupported_host_uses_c(self):
        self.build_run(['-DLPX4_ENABLE_ASM=1','-DLPX4_ARCH=LPX4_ARCH_AVR5'])


if __name__ == '__main__':
    unittest.main()
