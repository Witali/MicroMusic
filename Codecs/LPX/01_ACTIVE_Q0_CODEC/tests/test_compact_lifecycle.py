"""Public lifecycle trace frozen before narrowing compact private state."""
import subprocess,tempfile,unittest
from pathlib import Path
from speech_compact import repack
from test_speech_v4 import fixture
ROOT=Path(__file__).resolve().parents[1]
# Generated with the corrected b8f473a6 decoder and this exact synthetic probe.
FROZEN={4:'0df165929f4fce41',6:'da22418e77222f83'}
class CompactLifecycleTests(unittest.TestCase):
    def test_headers_errors_copies_counters_and_all_legal_count_arithmetic(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            inputs={p:folder/f'profile{p}.l4hy' for p in (4,6)}
            for p,path in inputs.items():path.write_bytes(repack(fixture(p,64000))[0])
            for only in (0,1):
                for batched in (0,1):
                    for rom in (0,1):
                        exe=folder/f'life-{only}-{batched}-{rom}.exe'
                        flags=['-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
                            f'-DLPX4_COMPACT_ONLY={only}',f'-DLPX4_BATCHED_REMAINING={batched}',
                            f'-DLPX4_ROM_POINTER={rom}']
                        subprocess.run(['g++','-O2','-std=c++11',*flags,'-I'+str(ROOT/'src'),
                            str(ROOT/'tests/compact_lifecycle.cpp'),str(ROOT/'src/Lpx4HybridCore.cpp'),
                            '-o',str(exe)],check=True,capture_output=True)
                        for p,path in inputs.items():
                            self.assertEqual(subprocess.check_output([str(exe),str(path)],text=True).strip(),FROZEN[p])
if __name__=='__main__':unittest.main()
