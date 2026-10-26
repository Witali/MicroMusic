import struct,subprocess,tempfile,unittest
from pathlib import Path
from lpx4 import encode
from wav_lpc import pack_frames
ROOT=Path(__file__).resolve().parents[1]

class SampleCounterTests(unittest.TestCase):
    def test_boundaries_restart_and_32bit_duration(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);exe=folder/'counter.exe'
            subprocess.run(['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),
                str(ROOT/'tests/sample_counters.cpp'),str(ROOT/'src/Lpx4HybridCore.cpp'),
                '-o',str(exe)],check=True,capture_output=True)
            vector=[round(1023*i/11) for i in range(1,11)]
            for count in (1,19,20,39,40,79,80,159,160,161,65535,65536,65537,131073):
                raw=struct.pack('<4sBBHIHHHH',b'L3AV',1,3,8000,count,0,0,160,80)
                doc={'raw':raw,'frames':pack_frames([vector]*((count+159)//160)),
                    'blocks':[{'bits':0,'scale':180,'q':[0]*min(80,count-i)} for i in range(0,count,80)]}
                blob=encode(doc,fast=True)[0];self.assertLessEqual(len(blob),65535)
                path=folder/'input.l4hy';path.write_bytes(blob)
                subprocess.run([str(exe),str(path)],check=True,capture_output=True)

if __name__=='__main__':unittest.main()
