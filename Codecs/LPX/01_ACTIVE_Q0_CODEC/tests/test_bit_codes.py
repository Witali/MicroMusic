import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class BitCodeTests(unittest.TestCase):
    def test_all_prefixes_offsets_eof_and_sticky_errors(self):
        for flags in (['-DLPX4_FAST_HUFFMAN3=0'],['-DLPX4_FAST_HUFFMAN3=1'],
                      ['-DLPX4_FAST_HUFFMAN3=1','-DLPX3_COST_INSTRUMENT=1']):
            with self.subTest(flags=flags),tempfile.TemporaryDirectory() as td:
                exe=Path(td)/'codes.exe'
                subprocess.run(['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),*flags,
                    str(ROOT/'tests/bit_codes.cpp'),'-o',str(exe)],check=True,capture_output=True)
                self.assertEqual(subprocess.check_output([str(exe)],text=True).strip(),
                    '526843 bit-code states exact')

if __name__=='__main__':unittest.main()
