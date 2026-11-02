"""Sparse80 parser: exact expansion, tails, strict flags and opt-in guards."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from batch_decoder import BatchDecoder,ROOT

REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT.parent/'research/lpx-s15-2026-11-01'))
from speech_sparse80 import expand,decode_model,pack
from test_s15 import fixture
from standard_metrics import pwm_duties


def native(output,compiler,segments,*,sparse80=False,compact=True,source=None,defines=()):
    source=ROOT/'src' if source is None else Path(source)
    flags=['-O2','-std=c++11','-shared','-fPIC','-DLPX4_ENABLE_ASM=0',
           '-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
           f'-DLPX3_LPC_SEGMENTS={segments}',*defines]
    if compact:flags.append('-DLPX4_COMPACT_ONLY=1')
    if sparse80:flags.append('-DLPX4_ENABLE_SPARSE80=1')
    # clang targeting the Windows MSVC linker needs explicit DLL exports.
    if os.name=='nt':flags+=['-Wl,/export:lpx4_batch_decode','-Wl,/export:lpx4_batch_decode_s16']
    result=subprocess.run([compiler,*flags,'-I'+str(source),source/'Lpx4HybridCore.cpp',
                           source/'native_batch_decoder.cpp','-o',output],capture_output=True)
    output.with_suffix('.log').write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('Native build failed; inspect '+str(output.with_suffix('.log')))
    return BatchDecoder(output)


class Sparse80DirectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.compiler=os.environ.get('LPX_NATIVE_CXX','g++')
        cls.root=Path(cls.folder.name)
        cls.pairs={s:(native(cls.root/f'common{s}.so',cls.compiler,s,compact=False),
                      native(cls.root/f'direct{s}.so',cls.compiler,s,sparse80=True),
                      native(cls.root/f'v5{s}.so',cls.compiler,s)) for s in (1,2,4)}

    @classmethod
    def tearDownClass(cls):cls.pairs.clear();cls.folder.cleanup()

    def test_full_pcm_pwm_expansion_and_old_v5(self):
        public=REPO/'web-player/audio/lpx-bread'
        for segments,(common,direct,v5) in self.pairs.items():
            for blob in [fixture(n) for n in (1,19,20,79,80,81,159,160,319,320,321,641)]+[(public/'low15.lpx').read_bytes()]:
                n=int.from_bytes(blob[8:12],'little');expanded=expand(blob)
                expected=common.decode_one_s16(expanded,n)
                self.assertIsNotNone(expected)
                np.testing.assert_array_equal(direct.decode_one_s16(blob,n),expected)
                np.testing.assert_array_equal(direct.decode_one(blob,n),pwm_duties(expected))
                if segments==2:np.testing.assert_array_equal(expected,decode_model(blob))
                self.assertIsNone(v5.decode_one(blob,n))
                self.assertIsNone(common.decode_one(blob,n))
            for name in ('compact.lpx','quality.lpx'):
                blob=(public/name).read_bytes();n=int.from_bytes(blob[8:12],'little')
                np.testing.assert_array_equal(direct.decode_one_s16(blob,n),v5.decode_one_s16(blob,n))
                np.testing.assert_array_equal(direct.decode_one(blob,n),v5.decode_one(blob,n))

    def test_fixed_sparse80_sram512_matches_expansion_and_rejects_other_headers(self):
        fixed=native(self.root/'fixed-sram512.so',self.compiler,2,sparse80=True,defines=(
            '-include',str(ROOT/'profiles/Lpx4Sram512.h'),'-DLPX4_FIXED_SPEECH_FLAGS=15',
            '-DLPX4_FIXED_PRE_Q14=8192','-DLPX4_FIXED_BRIGHT_Q14=11469'))
        common=self.pairs[2][0]
        for complete in (320,640):
            blob=fixture(complete);expected=common.decode_one_s16(expand(blob),complete)
            for n in range(complete-319,complete+1):
                tail=bytearray(blob);tail[8:12]=n.to_bytes(4,'little')
                np.testing.assert_array_equal(fixed.decode_one_s16(bytes(tail),n),expected[:n])
                np.testing.assert_array_equal(fixed.decode_one(bytes(tail),n),pwm_duties(expected[:n]))
        blob=fixture(320)
        for offset,value in ((12,8193),(14,11468)):
            bad=bytearray(blob);bad[offset:offset+2]=value.to_bytes(2,'little')
            self.assertIsNone(fixed.decode_one(bytes(bad),320))
        for name in ('compact.lpx','quality.lpx'):
            blob=(REPO/'web-player/audio/lpx-bread'/name).read_bytes()
            self.assertIsNone(fixed.decode_one(blob,int.from_bytes(blob[8:12],'little')))

    def test_all_final_packet_sample_tails(self):
        for common,direct,_ in self.pairs.values():
            for complete in (320,640):
                blob=fixture(complete);expected=common.decode_one_s16(expand(blob),complete)
                for n in range(complete-319,complete+1):
                    tail=bytearray(blob);tail[8:12]=n.to_bytes(4,'little');tail=bytes(tail)
                    np.testing.assert_array_equal(direct.decode_one_s16(tail,n),expected[:n])
                    np.testing.assert_array_equal(direct.decode_one(tail,n),pwm_duties(expected[:n]))

    def test_malformed_tail_and_v5_flag_rejection(self):
        from speech_sparse80 import unpack
        from s15_format import pack as historical_pack
        for _,direct,_ in self.pairs.values():
            for n in (1,20,79,80,159,160,319,320):
                blob=fixture(n);bad=[blob[:i] for i in range(22)]
                for cut in (1,2,3):
                    item=bytearray(blob[:-cut]);item[20:22]=(len(item)-22).to_bytes(2,'little');bad.append(bytes(item))
                item=bytearray(blob+b'\0');item[20:22]=(len(item)-22).to_bytes(2,'little');bad.append(bytes(item))
                _,meta=historical_pack(*unpack(blob))
                if meta['padding_bits']:
                    item=bytearray(blob);item[-1]|=128;bad.append(bytes(item))
                for offset in (4,5,6,16,18):
                    item=bytearray(blob);item[offset]^=1;bad.append(bytes(item))
                for item in bad:self.assertIsNone(direct.decode_one_s16(item,n))
            for name in ('compact.lpx','quality.lpx'):
                item=bytearray((REPO/'web-player/audio/lpx-bread'/name).read_bytes());item[5]|=64
                self.assertIsNone(direct.decode_one_s16(bytes(item),19200))

    def test_compile_guards(self):
        for settings in (['-DLPX4_ENABLE_SPARSE80=2'],['-DLPX4_ENABLE_SPARSE80=1']):
            result=subprocess.run([self.compiler,'-std=c++11',*settings,'-I'+str(ROOT/'src'),
                    '-x','c++','-fsyntax-only','-'],input='#include "Lpx4HybridCore.h"\n',capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)

    def test_cursor_and_sample_counter_fallbacks(self):
        common=self.pairs[2][0]
        for batched,rom in ((0,0),(0,1),(1,0)):
            direct=native(self.root/f'fallback-{batched}-{rom}.so',self.compiler,2,
                          sparse80=True,defines=[f'-DLPX4_BATCHED_REMAINING={batched}',
                                               f'-DLPX4_ROM_POINTER={rom}'])
            for n in (1,19,20,79,80,81,159,160,161,319,320,321,641):
                blob=fixture(n)
                expected=common.decode_one_s16(expand(blob),n)
                np.testing.assert_array_equal(direct.decode_one_s16(blob,n),expected)
                np.testing.assert_array_equal(direct.decode_one(blob,n),pwm_duties(expected))

    def test_deterministic_random_spectra_and_parameter_boundaries(self):
        rng=np.random.default_rng(328)
        common,direct,_=self.pairs[2]
        for case in range(24):
            n=int(rng.integers(1,2001));frames=(n+319)//320
            spectra=[sorted(map(int,rng.choice(64,10,replace=False))) for _ in range(frames)]
            params=[(int(rng.integers(32)),int(rng.integers(18,146)),
                     2*int(rng.integers(8))) for _ in range(frames)]
            from speech_sparse80 import POSITIONS
            pulses=[(POSITIONS[int(rng.integers(64))],(-8,7)[int(rng.integers(2))])
                    for _ in range(frames*4)]
            blob=pack(n,spectra,params,pulses,(0,8192,16384)[case%3],
                      (0,11469)[case%2])
            expected=common.decode_one_s16(expand(blob),n)
            self.assertIsNotNone(expected)
            np.testing.assert_array_equal(direct.decode_one_s16(blob,n),expected)
            np.testing.assert_array_equal(direct.decode_one(blob,n),pwm_duties(expected))


if __name__=='__main__':unittest.main()
