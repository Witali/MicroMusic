"""Check the trailing-unit simplification through the actual compiled recurrence."""
import hashlib,subprocess,tempfile,unittest
from pathlib import Path

class PolynomialUnitTests(unittest.TestCase):
    def test_full_signed_coefficient_edges_and_split_rounding(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'polynomial-unit.exe'
            subprocess.run(['g++','-O2','-std=c++11','-I'+str(root/'src'),
                str(root/'tests/polynomial_unit.cpp'),'-o',str(exe)],check=True,capture_output=True)
            self.assertEqual(subprocess.check_output([str(exe)],text=True).strip(),
                             '564288 polynomial factors exact')

    def test_ordered_extreme_spectra_match_frozen_coefficients(self):
        # Independent baseline 3f717df5:4096 vectors *17 anchors *10 s16 words.
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'ordered-anchors.exe'
            subprocess.run(['g++','-O2','-std=c++11','-I'+str(root/'src'),
                str(root/'tests/ordered_anchor_coefficients.cpp'),'-o',str(exe)],check=True,capture_output=True)
            data=subprocess.check_output([str(exe)])
        self.assertEqual(len(data),1392640)
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         '1b47e930772e2b9194c95e13b448c73448e4933be98b3b4f1251a3aa9719d60d')

if __name__=='__main__':unittest.main()
