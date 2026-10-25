import subprocess
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]


class BitReaderTests(unittest.TestCase):
    def test_all_bytes_offsets_widths_and_residual_state(self):
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'reader.exe'
            subprocess.run(['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),
                str(ROOT/'tests/bit_reader.cpp'),'-o',str(exe)],
                check=True,capture_output=True)
            self.assertEqual(subprocess.check_output([str(exe)],text=True).strip(),'4718592 reader cases')


if __name__=='__main__':unittest.main()
