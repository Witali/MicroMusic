"""Version10 integer scale ramp: independent PCM/PWM, tails and copied state."""
import ctypes as ct
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import numpy as np
from batch_decoder import BatchDecoder, ROOT
from lpx4 import BitWriter
from speech_compact import put_spectrum
from speech_scale_ramp import pack, unpack, decode_model, payload_adapter
from speech_sparse80 import POSITIONS as POSITIONS80
from speech_v4 import POSITIONS4
from standard_metrics import pwm_duties
from test_sparse80_direct import native


def fixture(n, mode, seed=10, pre=13926, bright=0):
    rng = np.random.default_rng(seed)
    frames = (n+319)//320
    maximum, block, group, positions = (32,160,20,POSITIONS4) if mode == 4 else (64,320,80,POSITIONS80)
    spectra = [sorted(map(int,rng.choice(maximum,10,replace=False))) for _ in range(frames)]
    scales = (0,6,31,0,17,30,6,0)
    params = [(scales[i % len(scales)], (18,145,79)[i % 3], (0,14,6)[i % 3]) for i in range(frames*320//block)]
    pulses = [(int(positions[int(rng.integers(len(positions)))]),(-8,8 if mode==4 else 7)[int(rng.integers(2))])
              for _ in range(frames*320//group)]
    return pack(n,mode,spectra,params,pulses,pre,bright)


COPY_SOURCE = r'''
#include "Lpx4HybridCore.h"
#include "native_batch_decoder.cpp"
#ifdef _WIN32
#define EXPORTED __declspec(dllexport)
#else
#define EXPORTED
#endif
extern "C" EXPORTED int ramp_copy_reset(const uint8_t* data,uint16_t bytes,uint32_t split,const int16_t* expected,uint32_t n){
 Lpx4HybridCore a;int16_t first,second;
 if(!a.begin(data,bytes)||a.samples()!=n||split>n)return 1;
 for(uint32_t i=0;i<split;i++)if(!a.nextS16(first)||first!=expected[i])return 2;
 Lpx4HybridCore b=a;
 for(uint32_t i=split;i<n;i++)if(!a.nextS16(first)||!b.nextS16(second)||first!=second||first!=expected[i])return 3;
 if(!a.finished()||!b.finished())return 4;
 if(!a.begin(data,bytes))return 5;
 for(uint32_t i=0;i<n;i++)if(!a.nextS16(first)||first!=expected[i])return 6;
 if(!a.begin(data,bytes)||!a.nextS16(first))return 7;
 const uint8_t invalid[20]={0};
 if(a.begin(invalid,sizeof(invalid))||!a.begin(data,bytes))return 8;
 for(uint32_t i=0;i<n;i++)if(!a.nextS16(first)||first!=expected[i])return 9;
 return a.finished()?0:10;
}
'''


class ScaleRampDirectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.directory = Path(cls.temp.name)
        cls.compiler = os.environ.get('LPX_NATIVE_CXX','g++')
        cls.receivers = {q4: native(cls.directory/f'ramp-{q4}.so',cls.compiler,2,sparse80=True,
            defines=['-DLPX4_ENABLE_SCALE_RAMP=1',f'-DLPX4_EXCITATION_Q4={q4}']) for q4 in (0,1)}
        cls.old = native(cls.directory/'old.so',cls.compiler,2,sparse80=True)

    @classmethod
    def tearDownClass(cls):
        cls.receivers.clear();cls.old=None;cls.temp.cleanup()

    def test_independent_model_pcm_pwm_and_q4_equivalence(self):
        for mode in (4,15):
            for index,n in enumerate((1,19,20,39,40,79,80,81,159,160,161,319,320,321,641,1280)):
                blob=fixture(n,mode,seed=index,pre=(0,8192,16384)[index%3],bright=(0,11469)[index%2])
                expected=decode_model(blob)
                for receiver in self.receivers.values():
                    np.testing.assert_array_equal(receiver.decode_one_s16(blob,n),expected)
                    np.testing.assert_array_equal(receiver.decode_one(blob,n),pwm_duties(expected))
                self.assertIsNone(self.old.decode_one_s16(blob,n))

    def test_every_terminal_packet_tail(self):
        for mode in (4,15):
            for total in (320,640):
                blob=fixture(total,mode);expected=decode_model(blob)
                for n in range(total-319,total+1):
                    tail=bytearray(blob);tail[8:12]=n.to_bytes(4,'little');tail=bytes(tail)
                    for receiver in self.receivers.values():
                        np.testing.assert_array_equal(receiver.decode_one_s16(tail,n),expected[:n])

    def test_malformed_packets_and_old_flags_remain_strict(self):
        direct=self.receivers[1]
        for mode in (4,15):
            for n in (1,20,40,80,159,160,161,319,320,321):
                blob=fixture(n,mode)
                bad=[blob[:i] for i in range(22)]
                for cut in (1,2,3,7):
                    item=bytearray(blob[:-cut]);item[20:22]=(len(item)-22).to_bytes(2,'little');bad.append(bytes(item))
                item=bytearray(blob+b'\0');item[20:22]=(len(item)-22).to_bytes(2,'little');bad.append(bytes(item))
                writer,previous=BitWriter(),None
                for vector in unpack(blob)[2]:
                    put_spectrum(writer,list(vector),previous,5 if mode==4 else 6);previous=list(vector)
                padding=(-(writer.total+(110 if mode==4 else 43)*len(unpack(blob)[2])))%8
                if padding:
                    item=bytearray(blob);item[-1]|=1<<(8-padding);bad.append(bytes(item))
                for at in (4,5,6,16,18):
                    item=bytearray(blob);item[at]^=1;bad.append(bytes(item))
                for item in bad:self.assertIsNone(direct.decode_one_s16(item,n))
                ordinary=payload_adapter(blob)
                np.testing.assert_array_equal(direct.decode_one_s16(ordinary,n),self.old.decode_one_s16(ordinary,n))
                item=bytearray(ordinary);item[5]|=16
                self.assertIsNone(direct.decode_one_s16(bytes(item),n))

    def test_pointer_counter_fallbacks_and_maximum_length(self):
        for batched,rom in ((0,0),(0,1),(1,0)):
            receiver=native(self.directory/f'fallback-{batched}-{rom}.so',self.compiler,2,sparse80=True,
                defines=['-DLPX4_ENABLE_SCALE_RAMP=1',f'-DLPX4_BATCHED_REMAINING={batched}',f'-DLPX4_ROM_POINTER={rom}'])
            for mode in (4,15):
                for n in (1,159,160,161,319,320,321,641):
                    blob=fixture(n,mode);np.testing.assert_array_equal(receiver.decode_one_s16(blob,n),decode_model(blob))
        for mode in (4,15):
            blob=fixture(64000,mode)
            np.testing.assert_array_equal(self.receivers[1].decode_one_s16(blob,64000),decode_model(blob))

    def test_copied_in_progress_and_reset_after_success_or_bad_begin(self):
        source=self.directory/'copy.cpp';source.write_text(COPY_SOURCE,encoding='utf-8')
        library=self.directory/'copy.so'
        flags=['-O2','-std=c++11','-shared','-fPIC','-DLPX4_ENABLE_ASM=0','-DLPX4_ENABLE_SPEECH=1',
            '-DLPX4_ENABLE_SPEECH_COMPACT=1','-DLPX4_COMPACT_ONLY=1','-DLPX4_ENABLE_SPARSE80=1','-DLPX4_ENABLE_SCALE_RAMP=1']
        if os.name=='nt':flags+=['-Wl,/export:lpx4_batch_decode','-Wl,/export:lpx4_batch_decode_s16']
        result=subprocess.run([self.compiler,*flags,'-I'+str(ROOT/'src'),ROOT/'src/Lpx4HybridCore.cpp',source,'-o',library],capture_output=True)
        (self.directory/'copy.log').write_bytes(result.stdout+result.stderr);self.assertEqual(result.returncode,0)
        receiver=BatchDecoder(library);check=receiver.dll.ramp_copy_reset
        check.argtypes=[ct.POINTER(ct.c_uint8),ct.c_uint16,ct.c_uint32,ct.POINTER(ct.c_int16),ct.c_uint32];check.restype=ct.c_int
        for mode in (4,15):
            blob=fixture(641,mode);raw=np.frombuffer(blob,np.uint8);expected=decode_model(blob)
            for split in (0,1,19,20,39,40,79,80,159,160,161,319,320,640,641):
                self.assertEqual(check(raw.ctypes.data_as(ct.POINTER(ct.c_uint8)),len(blob),split,
                    expected.ctypes.data_as(ct.POINTER(ct.c_int16)),641),0)

    def test_compile_guards_and_sparse_backend_opt_in(self):
        for flags in (['-DLPX4_ENABLE_SCALE_RAMP=2'],['-DLPX4_ENABLE_SCALE_RAMP=1']):
            result=subprocess.run([self.compiler,'-std=c++11',*flags,'-I'+str(ROOT/'src'),'-x','c++','-fsyntax-only','-'],
                input='#include "Lpx4HybridCore.h"\n',capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
        receiver=native(self.directory/'p4-only.so',self.compiler,2,defines=['-DLPX4_ENABLE_SCALE_RAMP=1'])
        self.assertIsNotNone(receiver.decode_one_s16(fixture(640,4),640))
        self.assertIsNone(receiver.decode_one_s16(fixture(640,15),640))


if __name__=='__main__':unittest.main()
