import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class LsfNormTests(unittest.TestCase):
    def test_all_lsf10_values_and_17_anchor_positions(self):
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'lsf.exe'
            subprocess.run(['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),
                str(ROOT/'tests/lsf_norm.cpp'),'-o',str(exe)],check=True,capture_output=True)
            self.assertEqual(subprocess.check_output([str(exe)],text=True).strip(),
                '17825792 LSF anchors exact')

if __name__=='__main__':unittest.main()
