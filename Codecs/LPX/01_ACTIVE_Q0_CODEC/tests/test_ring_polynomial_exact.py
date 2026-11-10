"""Independent convolution, original cosine ROM and every workspace wrap."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class RingPolynomialExactTests(unittest.TestCase):
    def test_all_cursor_positions_and_reachable_anchors(self):
        with tempfile.TemporaryDirectory() as temporary:
            for segments in (1,2,4):
                executable=Path(temporary)/f'ring-polynomial-{segments}'
                command=['g++','-O2','-std=c++11','-fsanitize=undefined',
                         '-fno-sanitize-recover=all','-DLPX4_ENABLE_ASM=0',
                         '-DLPX4_COMPACT_VERSION=9',f'-DLPX3_LPC_SEGMENTS={segments}',
                         '-include',str(ROOT/'profiles/Lpx4Sram512.h'),
                         '-I'+str(ROOT/'src'),str(ROOT/'tests/ring_polynomial_exact.cpp'),
                         '-o',str(executable)]
                subprocess.run(command,check=True,capture_output=True)
                result=subprocess.check_output([str(executable)],text=True)
                expected=3*48*(segments+1)*256
                self.assertEqual(result.strip(),
                    f'{expected} conversions exact; all 256 cursors preserve 145 live slots')


if __name__=='__main__':unittest.main()
