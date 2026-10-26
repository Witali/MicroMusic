"""Fast dispatch retains exact PCM and instrumented reference bit costs."""
import json,subprocess,tempfile,unittest
from pathlib import Path
import numpy as np
from batch_decoder import BatchDecoder,ROOT
from compact_format import pack
from q0_model import decode_pcm16
from test_compact_format import source

class ExcitationPathTests(unittest.TestCase):
    def test_reference_and_fast_dispatch_match_pcm_and_bit_costs(self):
        original=source();samples=int.from_bytes(original[8:12],'little');expected=decode_pcm16(original)
        probes=[]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            folder=Path(td)
            for flags in (0,7):
                common=['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),'-DLPX4_V3_FEATURES=124',
                    '-DLPX4_FAST_EXCITATION='+str(flags)]
                dll=folder/f'fast{flags}.so'
                subprocess.run([*common,'-shared','-fPIC',str(ROOT/'src/Lpx4HybridCore.cpp'),
                    str(ROOT/'src/native_batch_decoder.cpp'),'-o',str(dll)],check=True,capture_output=True)
                exe=folder/f'probe{flags}.exe'
                subprocess.run([*common,'-DLPX3_COST_INSTRUMENT=1',str(ROOT/'src/Lpx4HybridCore.cpp'),
                    str(ROOT/'tests/decode_metrics.cpp'),'-o',str(exe)],check=True,capture_output=True)
                decoder=BatchDecoder(dll);metrics=[]
                for mask in (0,24,32,124):
                    blob=pack(original,mask)[0];path=folder/'input.l4hy';path.write_bytes(blob)
                    np.testing.assert_array_equal(decoder.decode_one_s16(blob,samples),expected)
                    metrics.append(json.loads(subprocess.check_output([str(exe),str(path)],text=True)))
                probes.append(metrics)
        self.assertEqual(probes[0],probes[1])

if __name__=='__main__':unittest.main()
