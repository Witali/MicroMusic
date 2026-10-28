"""Parser trace frozen against decoder3f717df5 before the bounded rewrite."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class CompactParserTests(unittest.TestCase):
    def test_full_header_and_bounded_spectrum_error_traces(self):
        # 1,838,989 cases per build include all16-bit span lengths with boundary
        # payloads; all payloads at20/21/22/65535; every flag/version with wide
        # sample-count failures and a following null begin; both Rice modes and
        # complete signed8 value domains; radix20/extras and selected EOF cuts.
        # Canonical words include public metadata/errors, residual reader state,
        # LSF/pulse state and diagnostics. Private flag storage is normalized.
        # Reference digests came from an immutable3f717df5 src snapshot compiled
        # with this exact probe with the same probe, not from these formulas.
        expected={0:'1838989 parser cases f349867a8a8be23a',
                  1:'1838989 parser cases 1add0d08489dfb2f'}
        with tempfile.TemporaryDirectory() as td:
            for only in (0,1):
                for rom in (0,1):
                    exe=Path(td)/f'compact-parser-{only}-{rom}.exe'
                    definitions=['-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
                        '-DLPX4_V3_FEATURES=124','-DLPX3_COST_INSTRUMENT=1',
                        f'-DLPX4_COMPACT_ONLY={only}',f'-DLPX4_ROM_POINTER={rom}']
                    subprocess.run(['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),
                        *definitions,str(ROOT/'tests/compact_parser.cpp'),'-o',str(exe)],
                        check=True,capture_output=True)
                    self.assertEqual(subprocess.check_output([str(exe)],text=True).strip(),expected[only])


if __name__=='__main__': unittest.main()
