import subprocess,tempfile,unittest
from pathlib import Path
import numpy as np
from batch_decoder import BatchDecoder,ROOT
from compact_format import pack
from q0_model import decode_pcm16
from test_compact_format import source
class AnchorModeTests(unittest.TestCase):
    def test_copy_rotate_segments_restart_and_snapshot_independence(self):
        original=source();samples=int.from_bytes(original[8:12],'little')
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            folder=Path(td)
            for segments in (1,2,4):
                reference=[]
                for rotate in (0,1):
                    args=['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),'-DLPX4_V3_FEATURES=124',
                        f'-DLPX4_ROTATE_LPC_ANCHORS={rotate}',f'-DLPX3_LPC_SEGMENTS={segments}']
                    dll=folder/f'anchors{segments}-{rotate}.so';exe=folder/f'copy{segments}-{rotate}.exe'
                    for extra,target in ((['-shared','-fPIC',str(ROOT/'src/native_batch_decoder.cpp')],dll),
                            ([str(ROOT/'tests/anchor_copy.cpp')],exe)):
                        built=subprocess.run([*args,*extra,str(ROOT/'src/Lpx4HybridCore.cpp'),'-o',str(target)],capture_output=True,text=True)
                        self.assertEqual(built.returncode,0,built.stderr)
                    decoder=BatchDecoder(dll)
                    for index,mask in enumerate((0,24,32,124)):
                        blob=pack(original,mask)[0];path=folder/'input.l4hy';path.write_bytes(blob)
                        actual=decoder.decode_one_s16(blob,samples);self.assertIsNotNone(actual)
                        if rotate==0:reference.append(actual.copy())
                        else:np.testing.assert_array_equal(actual,reference[index])
                        if segments==2:np.testing.assert_array_equal(actual,decode_pcm16(original))
                        np.testing.assert_array_equal(decoder.decode_one_s16(blob,samples),actual)
                        subprocess.run([str(exe),str(path)],check=True,capture_output=True)
if __name__=='__main__':unittest.main()
