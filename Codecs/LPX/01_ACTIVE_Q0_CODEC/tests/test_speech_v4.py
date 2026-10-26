import struct, subprocess, tempfile, unittest
from pathlib import Path
import numpy as np
from batch_decoder import BatchSession, BatchDecoder, ROOT
from speech_v4 import pack, unpack, decode_model, encode, POSITIONS4
from standard_metrics import pwm_duties


def fixture(profile,n=641):
    packets=(n+319)//320
    spectra=[[2+i*2+(fi&1) for i in range(10)] for fi in range(packets)]
    params=[(20+hi%4,18+hi%128,(hi%8)*2) for hi in range(packets*2)]
    pulses=[(int(POSITIONS4[i%16]) if profile==4 else i%20,
             (-8 if i&1 else 8) if profile==4 else i%16-8) for i in range(packets*16)]
    return pack(n,profile,spectra,params,pulses)


class SpeechV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',v3_features=24,speech=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):cls.session.__exit__()

    def test_model_pwm_partial_tails_and_no_opt_in(self):
        with BatchSession('batch',v3_features=24) as old:
            for p in (4,6):
                for n in (1,19,20,39,40,79,80,159,160,161,319,320,321,641,64000):
                    blob=fixture(p,n);expected=decode_model(blob)
                    self.assertEqual(len(blob),20+((n+319)//320)*(20 if p==4 else 30))
                    np.testing.assert_array_equal(self.decoder.decode_one_s16(blob,n),expected)
                    np.testing.assert_array_equal(self.decoder.decode_one(blob,n),pwm_duties(expected))
                    self.assertIsNone(old.decode_one(blob,n))

    def test_all_truncations_and_invalid_headers(self):
        for p in (4,6):
            blob=fixture(p)
            invalid=[blob[:cut] for cut in range(len(blob))]+[blob+b'\0']
            for field,value,size in ((4,5,1),(5,8,1),(6,16000,2),(8,0,4),
                                     (8,0xffffffff,4),(12,16385,2),(14,11470,2),
                                     (16,160,2),(18,80,2)):
                b=bytearray(blob);b[field:field+size]=value.to_bytes(size,'little');invalid.append(bytes(b))
            self.assertTrue(all(x is None for x in self.decoder.decode_many_s16(invalid,641)))

    def test_invalid_spectra_reserved_bits_and_positions(self):
        for p in (4,6):
            blob=bytearray(fixture(p,640))
            for bit in range(10 if p==4 else 12):blob[20+bit//8]&=255^(1<<(bit%8))
            self.assertIsNone(self.decoder.decode_one_s16(bytes(blob),640))
        blob=bytearray(fixture(6,640));blob[27]|=16 # reserved bits begin at bit60
        self.assertIsNone(self.decoder.decode_one_s16(bytes(blob),640))
        blob=bytearray(fixture(6,640))
        # First pulse follows 60 spectrum +6 reserved +15 parameter bits.
        for bit in range(81,86):blob[20+bit//8]|=1<<(bit%8)
        self.assertIsNone(self.decoder.decode_one_s16(bytes(blob),640))
        with self.assertRaises(ValueError):unpack(bytes(blob))

    def test_restart_snapshots_and_fallback_storage_flags(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            folder=Path(td)
            for flags in ([],['-DLPX4_EXCITATION_Q4=0','-DLPX4_LPC_RING=0',
                              '-DLPX4_ROTATE_LPC_ANCHORS=0','-DLPX4_BATCHED_REMAINING=0']):
                args=['g++','-O2','-std=c++11','-DLPX4_ENABLE_SPEECH=1',
                      '-I'+str(ROOT/'src'),*flags]
                dll=folder/'speech.so';exe=folder/'copy.exe'
                subprocess.run([*args,'-shared','-fPIC',str(ROOT/'src/native_batch_decoder.cpp'),
                    str(ROOT/'src/Lpx4HybridCore.cpp'),'-o',str(dll)],check=True,capture_output=True)
                subprocess.run([*args,str(ROOT/'tests/anchor_copy.cpp'),str(ROOT/'src/Lpx4HybridCore.cpp'),
                    '-o',str(exe)],check=True,capture_output=True)
                decoder=BatchDecoder(dll)
                for p in (4,6):
                    blob=fixture(p);path=folder/'input.l4hy';path.write_bytes(blob)
                    np.testing.assert_array_equal(decoder.decode_one_s16(blob,641),decode_model(blob))
                    subprocess.run([str(exe),str(path)],check=True,capture_output=True)
                del decoder
                # Loaded DLLs cannot be overwritten on Windows.
                dll=folder/'unused.so'
                if not flags:
                    # Use a new directory for the second storage configuration.
                    folder=folder/'fallback';folder.mkdir()

    def test_encoder_native_model_exact_and_silence(self):
        for p in (4,6):
            for x in (np.zeros(321,np.int16),
                      (1800*np.sin(np.arange(641)*.2)).astype(np.int16)):
                blob,pcm,r=encode(x,p,self.decoder)
                np.testing.assert_array_equal(pcm,decode_model(blob))
                self.assertTrue(r['native_model_exact'])


if __name__=='__main__':unittest.main()
