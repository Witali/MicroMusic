"""Exact portable-C word extraction against independent mathematical floors."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('g++'),'Requires the native C++ compiler')
class FixedCMathTests(unittest.TestCase):
    def test_full_ranges_and_random_values_with_undefined_behavior_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            executable=Path(folder)/'fixed-c-math'
            subprocess.run(['g++','-O2','-std=c++11','-fsanitize=undefined',
                '-fno-sanitize-recover=undefined','-DLPX4_ENABLE_ASM=0',
                '-I'+str(ROOT/'src'),str(ROOT/'tests/fixed_c_math.cpp'),
                '-o',str(executable)],check=True,capture_output=True)
            result=subprocess.run([str(executable)],check=True,capture_output=True,text=True)
            self.assertIn('shifts=2983059',result.stdout)
            self.assertIn('random_full_q14=2000000',result.stdout)
            self.assertIn('attenuations=1703936',result.stdout)
            self.assertIn('pwm=16777216',result.stdout)


if __name__=='__main__':unittest.main()
