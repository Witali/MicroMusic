import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class UnaryReaderTests(unittest.TestCase):
    def test_cached_reference_table_and_instrumented_states(self):
        with tempfile.TemporaryDirectory() as td:
            for variant in (0,1,2):
                exe=Path(td)/f'unary{variant}.exe'
                built=subprocess.run(['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),
                    '-DLPX3_COST_INSTRUMENT=1',f'-DLPX4_FAST_UNARY={variant}',
                    str(ROOT/'tests/unary_reader.cpp'),'-o',str(exe)],capture_output=True,text=True)
                self.assertEqual(built.returncode,0,built.stderr)
                self.assertEqual(subprocess.check_output([str(exe)],text=True).strip(),'784896 unary states')
if __name__=='__main__':unittest.main()
