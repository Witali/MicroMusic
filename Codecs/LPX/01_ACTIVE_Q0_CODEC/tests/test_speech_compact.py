import subprocess,tempfile,unittest
from pathlib import Path
import numpy as np
from batch_decoder import BatchSession,ROOT
from test_speech_v4 import fixture
from standard_metrics import pwm_duties
from speech_compact import pack,repack,unpack,decode_model,components,put_spectrum
from speech_v4 import unpack as unpack4


class CompactSpeechTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session=BatchSession('batch',v3_features=24,speech=True,speech_compact=True)
        cls.decoder=cls.session.__enter__()

    @classmethod
    def tearDownClass(cls):cls.session.__exit__()

    def test_exact_fields_pcm_pwm_partial_and_opt_in(self):
        with BatchSession('batch',speech=True) as old:
            for profile in (4,6):
                for n in (1,19,20,39,40,159,160,319,320,321,641,64000):
                    original=fixture(profile,n);packed,report=repack(original)
                    self.assertEqual(unpack(packed)[:7],components(original))
                    expected=self.decoder.decode_one_s16(original,n)
                    np.testing.assert_array_equal(self.decoder.decode_one_s16(packed,n),expected)
                    np.testing.assert_array_equal(decode_model(packed),expected)
                    np.testing.assert_array_equal(self.decoder.decode_one(packed,n),pwm_duties(expected))
                    self.assertIsNone(old.decode_one(packed,n))

    def test_every_radix20_pair_and_collision_extra_sums(self):
        original=fixture(6,16000);args=list(components(original));pulses=list(args[4])
        for i in range(400):pulses[i*2:i*2+2]=[(i%20,5),(i//20,-3)]
        args[4]=pulses
        # Cover all pair values; extras collide with first, second or neither.
        extras=[(pulses[i*2][0],7) if i%3==0 else
                (20+pulses[i*2+1][0],-8) if i%3==1 else (39,4) for i in range(400)]
        packed,report=pack(*args,extras=extras)
        self.assertEqual(unpack(packed)[4],pulses)
        self.assertEqual(unpack(packed)[7],extras)
        np.testing.assert_array_equal(self.decoder.decode_one_s16(packed,16000),decode_model(packed))
        self.assertEqual(report['extra_pulses'],400)

    def test_truncation_length_initial_modes_and_corrupt_pairs(self):
        for p in (4,6):
            b=repack(fixture(p))[0]
            invalid=[b[:i] for i in range(len(b))]+[b+b'\0']
            for value in (0,65535):
                x=bytearray(b);x[20:22]=value.to_bytes(2,'little');invalid.append(bytes(x))
            # Repeat and delta modes before a previous spectrum exists.
            for mode in (0,3):
                x=bytearray(b);x[22]=(x[22]&252)|mode;invalid.append(bytes(x))
            self.assertTrue(all(x is None for x in self.decoder.decode_many_s16(invalid,641)))
        # Locate pair/extra fields with an independent spectrum bit count.
        from lpx4 import BitWriter
        args=components(fixture(6,640));w=BitWriter();put_spectrum(w,args[2][0],None,6)
        start=w.total+15
        for target,width in ((start,9),(start+17+1,6)):
            b=bytearray(repack(fixture(6,640),force_extras=True)[0])
            if width==6:
                marker=start+17;b[22+marker//8]|=1<<(marker%8)
            for bit in range(target,target+width):b[22+bit//8]|=1<<(bit%8)
            self.assertIsNone(self.decoder.decode_one_s16(bytes(b),640))
        with self.assertRaises(ValueError):unpack(bytes(b))

    def test_restart_snapshots_and_header_build_guards(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root=Path(td);exe=root/'copy.exe'
            args=['g++','-O2','-std=c++11','-I'+str(ROOT/'src'),
                  '-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1']
            for reference in (False,True):
                flags=['-DLPX4_ROM_POINTER=0','-DLPX4_BATCHED_REMAINING=0',
                       '-DLPX4_LPC_RING=0','-DLPX4_EXCITATION_Q4=0',
                       '-DLPX4_ROTATE_LPC_ANCHORS=0'] if reference else []
                exe=root/('reference.exe' if reference else 'copy.exe')
                subprocess.run([*args,*flags,str(ROOT/'tests/anchor_copy.cpp'),str(ROOT/'src/Lpx4HybridCore.cpp'),
                                '-o',str(exe)],check=True,capture_output=True)
                for p in (4,6):
                    blob=repack(fixture(p),extras=[(i%40,-8 if i&1 else 7) for i in range(24)])[0]
                    path=root/'input.l4hy';path.write_bytes(blob)
                    subprocess.run([str(exe),str(path)],check=True,capture_output=True)
            for definitions in (['-DLPX4_ENABLE_SPEECH_COMPACT=2'],['-DLPX4_ENABLE_SPEECH_COMPACT=1']):
                result=subprocess.run(['g++','-std=c++11','-I'+str(ROOT/'src'),*definitions,
                    '-x','c++','-fsyntax-only','-'],input='#include "Lpx4HybridCore.h"\n',capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)

    def test_complete_packet_trailing_data_and_short_profiler_inputs(self):
        from profile_avr import run
        for p in (4,6):
            b=bytearray(repack(fixture(p,320))[0]);b.append(0)
            b[20:22]=(len(b)-22).to_bytes(2,'little')
            self.assertIsNone(self.decoder.decode_one_s16(bytes(b),320))
            with self.assertRaises(ValueError):unpack(bytes(b))
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'bad.l4hy'
            for b in (b'L4HY\x04',b'L4HY\x05'):
                f.write_bytes(b)
                with self.assertRaises(ValueError):
                    run(f,Path(td)/'unused',Path(td),Path(td)/'unused',speech=True,speech_compact=True)

    def test_extra_before_first_and_between_base_pulses(self):
        for p in (4,6):
            args=list(components(fixture(p,641)));args[4]=[(15,8 if p==4 else 5)]*48
            extras=[(0,7) if i&1 else (20,-8) for i in range(24)]
            b,_=pack(*args,extras=extras)
            np.testing.assert_array_equal(self.decoder.decode_one_s16(b,641),decode_model(b))


if __name__=='__main__':unittest.main()
