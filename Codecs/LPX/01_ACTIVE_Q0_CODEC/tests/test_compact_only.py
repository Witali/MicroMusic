import subprocess, tempfile, unittest
from pathlib import Path
import numpy as np
from batch_decoder import BatchSession, BatchDecoder, ROOT, build_library
from test_speech_v4 import fixture
from test_compact_format import source
from compact_format import pack as pack3
from speech_compact import components, pack, repack, decode_model, put_spectrum
from standard_metrics import pwm_duties


class CompactOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full_session=BatchSession('batch',v3_features=124,speech=True,speech_compact=True)
        cls.only_session=BatchSession('batch',v3_features=124,speech=True,speech_compact=True,compact_only=True)
        cls.full=cls.full_session.__enter__();cls.only=cls.only_session.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.only_session.__exit__();cls.full_session.__exit__()

    def test_default_legacy_support_and_explicit_only_rejection(self):
        legacy=source();n=int.from_bytes(legacy[8:12],'little')
        for blob in (legacy,pack3(legacy,24)[0],pack3(legacy,124)[0]):
            self.assertIsNotNone(self.full.decode_one_s16(blob,n))
            self.assertIsNone(self.only.decode_one_s16(blob,n))
        for p in (4,6):
            self.assertIsNotNone(self.full.decode_one_s16(fixture(p),641))
            self.assertIsNone(self.only.decode_one_s16(fixture(p),641))

    def test_v5_plain_extras_full_pwm_model_and_partial_tails(self):
        for profile in (4,6):
            for n in (1,19,20,39,40,159,160,319,320,321,641,64000):
                original=fixture(profile,n)
                for enhanced in (False,True):
                    extras=[(i%40,-8 if i&1 else 7) for i in range(((n+319)//320)*8)] if enhanced else None
                    blob,_=repack(original,extras=extras);expected=decode_model(blob)
                    np.testing.assert_array_equal(self.only.decode_one_s16(blob,n),expected)
                    np.testing.assert_array_equal(self.full.decode_one_s16(blob,n),expected)
                    np.testing.assert_array_equal(self.only.decode_one(blob,n),pwm_duties(expected))

    def test_every_partial_packet_output_boundary(self):
        # v5 stores a whole 320-sample packet even for a shorter output tail.
        # At 180..280 the final half is active but still has unread pulses.
        for profile in (4,6):
            for complete in (320,640):
                blob,_=repack(fixture(profile,complete))
                expected=decode_model(blob)
                variants=[]
                for n in range(complete-319,complete+1):
                    tail=bytearray(blob);tail[8:12]=n.to_bytes(4,'little')
                    variants.append(bytes(tail))
                for decoder in (self.full,self.only):
                    for n,tail in zip(range(complete-319,complete+1),variants):
                        np.testing.assert_array_equal(decoder.decode_one_s16(tail,n),expected[:n])
                for n in range(complete-140,complete,20):
                    tail=variants[n-(complete-319)]
                    np.testing.assert_array_equal(decode_model(tail),expected[:n])

    def test_every_radix_pair_and_three_entry_merge_sort(self):
        args=list(components(fixture(6,16000)));pulses=list(args[4])
        for i in range(400):pulses[i*2:i*2+2]=[(i%20,5),(i//20,-3)]
        args[4]=pulses
        for kind in range(4):
            extras=[(pulses[i*2][0],7) if kind==0 else
                    (20+pulses[i*2+1][0],-8) if kind==1 else
                    (0,7) if kind==2 else (20,-8) for i in range(400)]
            blob,_=pack(*args,extras=extras)
            np.testing.assert_array_equal(self.only.decode_one_s16(blob,16000),decode_model(blob))

    def test_malformed_prefix_length_and_complete_packet_trailing_bits(self):
        for profile in (4,6):
            blob,_=repack(fixture(profile));invalid=[blob[:i] for i in range(len(blob))]+[blob+b'\0']
            for mode in (0,3):
                bad=bytearray(blob);bad[22]=(bad[22]&252)|mode;invalid.append(bytes(bad))
            for size in (0,65535):
                bad=bytearray(blob);bad[20:22]=size.to_bytes(2,'little');invalid.append(bytes(bad))
            self.assertTrue(all(x is None for x in self.only.decode_many_s16(invalid,641)))
            blob,meta=repack(fixture(profile,320))
            bad=bytearray(blob);bad.append(0);bad[20:22]=(len(bad)-22).to_bytes(2,'little')
            self.assertIsNone(self.only.decode_one_s16(bytes(bad),320))
            if meta['payload_bits']%8:
                bad=bytearray(blob);bad[-1]|=128
                self.assertIsNone(self.only.decode_one_s16(bytes(bad),320))
        # Invalid radix20 value and extra-pulse position: no legacy parser
        # or reduced pulse storage may accidentally accept these fields.
        from lpx4 import BitWriter
        args=components(fixture(6,640));w=BitWriter();put_spectrum(w,args[2][0],None,6)
        start=w.total+15
        for offset,width in ((start,9),(start+18,6)):
            blob=bytearray(repack(fixture(6,640),force_extras=True)[0])
            if width==6:blob[22+(start+17)//8]|=1<<((start+17)%8)
            for bit in range(offset,offset+width):blob[22+bit//8]|=1<<(bit%8)
            self.assertIsNone(self.only.decode_one_s16(bytes(blob),640))

    def test_reference_flags_restart_snapshots_and_removed_legacy_definitions(self):
        flags=['-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1','-DLPX4_COMPACT_ONLY=1']
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            folder=Path(td)
            reference=['-DLPX4_ROM_POINTER=0','-DLPX4_BATCHED_REMAINING=0',
                '-DLPX4_LPC_RING=0','-DLPX4_EXCITATION_Q4=0','-DLPX4_ROTATE_LPC_ANCHORS=0',
                '-DLPX4_FAST_PITCH=0','-DLPX4_FAST_EXCITATION=0']
            for index,settings in enumerate(([],reference)):
                args=['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),*flags,*settings]
                dll=folder/f'only{index}.so';exe=folder/f'copy{index}.exe'
                subprocess.run([*args,'-shared','-fPIC',str(ROOT/'src/native_batch_decoder.cpp'),
                    str(ROOT/'src/Lpx4HybridCore.cpp'),'-o',str(dll)],check=True,capture_output=True)
                subprocess.run([*args,str(ROOT/'tests/anchor_copy.cpp'),str(ROOT/'src/Lpx4HybridCore.cpp'),
                    '-o',str(exe)],check=True,capture_output=True)
                decoder=BatchDecoder(dll)
                for p in (4,6):
                    for n in (180,200,220,240,260,280,500,640,641):
                        blob=repack(fixture(p,n),extras=[(i%40,-8 if i&1 else 7) for i in range(((n+319)//320)*8)])[0]
                        path=folder/f'input{index}-{p}-{n}.l4hy';path.write_bytes(blob)
                        np.testing.assert_array_equal(decoder.decode_one_s16(blob,n),decode_model(blob))
                        subprocess.run([str(exe),str(path)],check=True,capture_output=True)
                        if n==640:
                            bad=bytearray(blob);bad.append(0);bad[20:22]=(len(bad)-22).to_bytes(2,'little')
                            self.assertIsNone(decoder.decode_one_s16(bytes(bad),n))
            processed=subprocess.run(['g++','-std=c++11','-E','-P','-I'+str(ROOT/'src'),*flags,
                str(ROOT/'src/Lpx4HybridCore.cpp')],check=True,capture_output=True,text=True).stdout
            for method in ('readBlock','readHuffman3','readUnary8'):
                self.assertNotIn('Lpx4HybridCore::'+method+'(',processed)

    def test_header_python_and_profiler_gates(self):
        for definitions in (['-DLPX4_COMPACT_ONLY=1'],
                ['-DLPX4_ENABLE_SPEECH=1','-DLPX4_COMPACT_ONLY=1'],
                ['-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1','-DLPX4_COMPACT_ONLY=2']):
            result=subprocess.run(['g++','-std=c++11','-I'+str(ROOT/'src'),*definitions,
                '-x','c++','-fsyntax-only','-'],input='#include "Lpx4HybridCore.h"\n',capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
        for kwargs in ({'compact_only':True},{'speech':True,'compact_only':True}):
            with self.assertRaises(ValueError):BatchSession('batch',**kwargs)
            with self.assertRaises(ValueError):build_library(Path('unused.so'),**kwargs)
        from profile_avr import run
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);path=folder/'legacy.l4hy';path.write_bytes(fixture(4))
            with self.assertRaises(ValueError):
                run(path,folder/'unused',folder,folder/'unused',speech=True,speech_compact=True,compact_only=True)
            self.assertFalse((folder/'unused').exists())


if __name__=='__main__':unittest.main()
