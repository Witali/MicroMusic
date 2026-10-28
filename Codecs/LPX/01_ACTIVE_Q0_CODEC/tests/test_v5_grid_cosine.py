"""V5-only cosine specialization retains exact reachable anchors and fallback."""
import hashlib,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
# Frozen legal-grid coefficients from decoder3f717df5, before specialization.
FROZEN={1:'82a9e8609c5ba6d75c5d6020fc2865a8e00c219086d02f126efe506b74a65782',
        2:'db3eda4b3e5ffe5326ff19d0c0abc2b41dbcca58be01dfe2338d211c4e3b35da',
        4:'0f1a0df2d4f4b9c11796d10197135678707c6bd076341ef1452965adf220bd33'}
class V5GridCosineTests(unittest.TestCase):
    def test_full_cosine_scalar_grid_and_frozen_lpc_for_each_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            for compact in (0,1):
                for segments in (1,2,4):
                    with self.subTest(compact_only=compact,lpc_segments=segments):
                        exe=Path(temporary)/f'grid-{compact}-{segments}.exe'
                        flags=['-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
                               f'-DLPX4_COMPACT_ONLY={compact}',f'-DLPX3_LPC_SEGMENTS={segments}','-DTEST_GRID=1']
                        subprocess.run(['g++','-O2','-std=c++11',*flags,'-I'+str(ROOT/'src'),
                                        str(ROOT/'tests/v5_grid_cosine.cpp'),'-o',str(exe)],check=True,capture_output=True)
                        result=subprocess.run([str(exe)],check=True,capture_output=True)
                        self.assertEqual(len(result.stdout),4096*(segments+1)*10*2)
                        self.assertEqual(hashlib.sha256(result.stdout).hexdigest(),FROZEN[segments])
                        self.assertEqual(result.stderr.decode().strip(),
                                         f'4096 cosine inputs, {5120*(segments+1)} scalar anchors exact')
if __name__=='__main__':unittest.main()
