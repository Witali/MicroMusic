"""Static LPC reuse must reload coefficients before each bandwidth expansion."""
import subprocess,tempfile,unittest
from pathlib import Path
import numpy as np
from batch_decoder import BatchDecoder,ROOT
from lpx4 import decode
from q0_model import coefficient_trace,synthesize,table
from test_compact_format import source

class BandwidthStorageTests(unittest.TestCase):
    def test_changed_static_zero_and_partial_frames_against_integer_model(self):
        blob=source();frames,blocks,q=decode(blob)
        co=coefficient_trace(frames,len(q))
        for gamma in (0,15360,16384):
            weights=[];weight=16384
            for _ in range(10):
                weight=(weight*gamma+8192)>>14;weights.append(weight)
            expanded=np.clip((co*np.array(weights)+8192)>>14,-32767,32767)
            expected=synthesize(np.asarray(q,np.int64),np.asarray([b['scale'] for b in blocks],np.int64),
                expanded,table('scale_table.inc'),int.from_bytes(blob[12:14],'little'),int.from_bytes(blob[14:16],'little'))
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
                dll=Path(td)/'expanded.so'
                subprocess.run(['g++','-O2','-shared','-fPIC','-std=c++11',
                    '-DLPX3_BANDWIDTH_EXPAND_Q14='+str(gamma),'-I'+str(ROOT/'src'),
                    str(ROOT/'src/Lpx4HybridCore.cpp'),str(ROOT/'src/native_batch_decoder.cpp'),
                    '-o',str(dll)],check=True,capture_output=True)
                actual=BatchDecoder(dll).decode_one_s16(blob,len(q))
                np.testing.assert_array_equal(actual,expected)

if __name__=='__main__':unittest.main()
