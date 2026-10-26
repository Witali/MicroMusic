"""Both public memory choices must decode partial/restarted streams identically."""
import subprocess,tempfile,unittest
from pathlib import Path
import numpy as np
from batch_decoder import BatchDecoder,ROOT
from q0_model import decode_pcm16
from test_compact_format import source
from compact_format import pack

class HistoryModeTests(unittest.TestCase):
    def test_linear_mirrored_and_c_fallback_match_model(self):
        original=source();samples=int.from_bytes(original[8:12],'little')
        expected=decode_pcm16(original)
        for mirrored,scaled in ((0,0),(0,1),(1,0),(1,1)):
            with self.subTest(mirrored=mirrored,scaled=scaled),tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
                dll=Path(td)/'history.so'
                subprocess.run(['g++','-O2','-shared','-fPIC','-std=c++11',
                    f'-DLPX4_LPC_RING={mirrored}',f'-DLPX4_EXCITATION_Q4={scaled}','-DLPX4_V3_FEATURES=124',
                    '-DLPX4_ENABLE_ASM=0','-I'+str(ROOT/'src'),str(ROOT/'src/Lpx4HybridCore.cpp'),
                    str(ROOT/'src/native_batch_decoder.cpp'),'-o',str(dll)],check=True,capture_output=True)
                decoder=BatchDecoder(dll)
                for features in (0,24,32,124):
                    blob=pack(original,features)[0]
                    for _ in range(2):
                        np.testing.assert_array_equal(decoder.decode_one_s16(blob,samples),expected)

if __name__=='__main__':unittest.main()
