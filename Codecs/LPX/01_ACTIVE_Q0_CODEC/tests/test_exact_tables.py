import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class ExactTableTests(unittest.TestCase):
    def test_actual_decoder_tables_exhaustively(self):
        with tempfile.TemporaryDirectory() as td:
            for compact in (False,True):
                with self.subTest(compact_only=compact):
                    exe=Path(td)/('tables-compact.exe' if compact else 'tables-common.exe')
                    definitions=['-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
                                 '-DLPX4_COMPACT_ONLY='+str(int(compact))]
                    subprocess.run(['g++','-O2','-std=c++11',*definitions,'-I'+str(ROOT/'src'),
                        str(ROOT/'tests/exact_tables.cpp'),'-o',str(exe)],check=True,capture_output=True)
                    self.assertEqual(subprocess.check_output([str(exe)],text=True).strip(),
                        ('32 compact scales' if compact else '256 scales')+
                        ', 4096 cosine interpolations exact')

if __name__=='__main__':unittest.main()
