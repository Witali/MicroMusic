"""The second v5 packet half reuses its LPC endpoint without copying LSFs."""
import subprocess,tempfile,unittest
from pathlib import Path
import numpy as np
from batch_decoder import BatchDecoder
from speech_compact import components,pack
from standard_metrics import pwm_duties
from test_speech_v4 import fixture
ROOT=Path(__file__).resolve().parents[1]
class V5HalfSpectrumTests(unittest.TestCase):
    def test_common_reference_segments_expansion_tails_and_snapshots(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            folder=Path(temporary)
            for segments in (1,2,4):
                for expand in (False,True):
                    flags=['-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
                           f'-DLPX3_LPC_SEGMENTS={segments}']
                    if expand:flags.append('-DLPX3_BANDWIDTH_EXPAND_Q14=16000')
                    decoders=[]
                    for compact in (0,1):
                        dll=folder/f'half-{segments}-{int(expand)}-{compact}.so'
                        args=['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),*flags,f'-DLPX4_COMPACT_ONLY={compact}']
                        subprocess.run([*args,'-shared','-fPIC',str(ROOT/'src/native_batch_decoder.cpp'),
                                        str(ROOT/'src/Lpx4HybridCore.cpp'),'-o',str(dll)],check=True,capture_output=True)
                        decoders.append(BatchDecoder(dll))
                    exe=folder/f'copy-{segments}-{int(expand)}.exe'
                    subprocess.run(['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),*flags,'-DLPX4_COMPACT_ONLY=1',
                                    str(ROOT/'tests/anchor_copy.cpp'),str(ROOT/'src/Lpx4HybridCore.cpp'),'-o',str(exe)],
                                   check=True,capture_output=True)
                    for profile in (4,6):
                        for n in (1,19,159,160,161,180,200,220,240,260,280,300,319,320,321,500,641,1280):
                            for pattern in (0,1,2):
                                fields=list(components(fixture(profile,n)))
                                spectra=fields[2]
                                if pattern==1:fields[2]=[spectra[0]]*len(spectra)
                                elif pattern==2:fields[2]=[spectra[(i//2)%2] if len(spectra)>1 else spectra[0] for i in range(len(spectra))]
                                extras=[(i%40,-8 if i&1 else 7) for i in range(len(spectra)*8)]
                                blob=pack(*fields,extras=extras)[0]
                                reference=decoders[0].decode_one_s16(blob,n);actual=decoders[1].decode_one_s16(blob,n)
                                np.testing.assert_array_equal(actual,reference)
                                np.testing.assert_array_equal(decoders[1].decode_one(blob,n),pwm_duties(reference))
                                if n==1280:
                                    path=folder/'input.l4hy';path.write_bytes(blob)
                                    subprocess.run([str(exe),str(path)],check=True,capture_output=True)
if __name__=='__main__':unittest.main()
