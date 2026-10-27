import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class ExactTableTests(unittest.TestCase):
    def test_actual_decoder_tables_exhaustively(self):
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'tables.exe'
            subprocess.run(['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),
                str(ROOT/'tests/exact_tables.cpp'),'-o',str(exe)],check=True,capture_output=True)
            self.assertEqual(subprocess.check_output([str(exe)],text=True).strip(),
                '256 scales, 4096 cosine interpolations exact')

if __name__=='__main__':unittest.main()
