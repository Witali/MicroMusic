"""Differential contracts for the explicit v5-only polynomial workspace profile.

Only a host C++ compiler and Python's standard library are needed. Optional
private streams may be supplied through LPX4_SRAM512_FIXTURES (a JSON path list).
"""
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CXX = shlex.split(os.environ.get('CXX', 'g++'))
HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <fstream>
#include <iterator>
#include <vector>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
#define private public
#include "Lpx4HybridCore.h"
#undef private
// One translation unit also supports MSVC-compatible access-level mangling.
#include "Lpx4HybridCore.cpp"

static std::vector<uint8_t> output(Lpx4HybridCore pcm,Lpx4HybridCore pwm){
    std::vector<uint8_t> result;
    int16_t s;uint8_t p;
    while(pcm.nextS16(s)){
        if(!pwm.next(p))return {};
        result.push_back((uint8_t)s);result.push_back((uint8_t)((uint16_t)s>>8));result.push_back(p);
    }
    if(pwm.next(p)||pcm.error()||pwm.error()||!pcm.finished()||!pwm.finished())return {};
    return result;
}
int main(int argc,char** argv){
#ifdef _WIN32
    if(_setmode(_fileno(stdout),_O_BINARY)==-1)return 24;
#endif
    if(argc==2&&!strcmp(argv[1],"--size")){printf("%zu\n",sizeof(Lpx4HybridCore));return 0;}
    if(argc<2)return 1;
    std::ifstream file(argv[1],std::ios::binary);
    std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(file)),{});
    Lpx4HybridCore pcm,pwm;
    if(!pcm.begin(bytes.data(),bytes.size())||!pwm.begin(bytes.data(),bytes.size()))return 2;
    if(argc==3){
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_SRAM512
        int16_t first;if(!pcm.nextS16(first))return 20;
        for(unsigned cursor=0;cursor<256;++cursor){
            for(unsigned t=0;t<=16;t+=16/LPX3_LPC_SEGMENTS){
                Lpx4HybridCore probe=pcm;
                probe.ringCursor_=(uint8_t)cursor;
                for(unsigned i=0;i<256;++i)probe.ringQ_[i]=(int8_t)((i*13)%64-32);
                int8_t original[256];memcpy(original,probe.ringQ_,256);
                int16_t out[10];probe.convertLsfAt((uint8_t)t,out);
                if(probe.ringCursor_!=cursor)return 21;
                // Inclusive maximum lag: these are exactly the 145 live slots.
                for(unsigned lag=1;lag<=145;++lag){
                    const uint8_t at=(uint8_t)(cursor-lag);
                    if(probe.ringQ_[at]!=original[at])return 22;
                }
            }
        }
        return 0;
#else
        return 23;
#endif
    }
    const auto expected=output(pcm,pwm);
    if(expected.size()!=3*pcm.samples())return 3;
    const unsigned cuts[]={1,18,39,40,144,145,146,159,160,254,255,256,257,509};
    for(unsigned cut:cuts){
        if(cut>=pcm.samples())continue;
        Lpx4HybridCore a=pcm,b=pwm;int16_t s;uint8_t p;
        for(unsigned i=0;i<cut;++i)if(!a.nextS16(s)||!b.next(p))return 4;
        Lpx4HybridCore copied(a),assigned;assigned=b;
        const auto suffix=output(copied,assigned);
        if(suffix!=std::vector<uint8_t>(expected.begin()+3*cut,expected.end()))return 5;
        // Reusing a partly consumed instance must discard all workspace state.
        if(!a.begin(bytes.data(),bytes.size())||!b.begin(bytes.data(),bytes.size())||output(a,b)!=expected)return 6;
    }
    fwrite(expected.data(),1,expected.size(),stdout);return 0;
}
'''


def fixture(profile, samples, lag, style='changing', extras=True):
    """Small independent legal gap/repeat writer, including bounded-Rice escapes."""
    bits = []

    def put(value, count):
        bits.extend((value >> i) & 1 for i in range(count))

    def rice(value, k, width):
        quotient = value >> k
        if quotient >= 8:
            put(0, 8)
            put(value, width)
        else:
            put(0, quotient)
            put(1, 1)
            put(value & ((1 << k) - 1), k)

    old = None
    width = 5 if profile == 4 else 6
    for frame in range((samples + 319) // 320):
        if style == 'static':
            vector = list(range(10))
        elif style == 'clusters':
            first = 0 if frame % 2 == 0 else (1 << width) - 10
            vector = list(range(first, first + 10))
        else:
            vector = [2 + i * 2 + frame % 2 for i in range(10)]
        if vector == old:
            put(0, 1)
        else:
            put(1, 1)
            put(0, 1)  # gap mode
            for value in [vector[0]] + [b - a - 1 for a, b in zip(vector, vector[1:])]:
                rice(value, 1 if profile == 4 else 2, width)
        old = vector
        for half in range(2):
            put(20 + (frame * 2 + half) % 4, 5)
            put(lag - 18, 7)
            put(7, 3)
            for group in range(4):
                index = frame * 8 + half * 4 + group
                if profile == 4:
                    for pulse in range(2):
                        put((index * 2 + pulse) % 16, 4)
                        put(pulse, 1)
                else:
                    a, b = (index * 2) % 20, (index * 2 + 1) % 20
                    put(a + 20 * b, 9)
                    put((index % 16 - 8) & 15, 4)
                    put((7 - index % 16) & 15, 4)
                if extras:
                    put(1, 1)
                    put(index % 40, 6)
                    put((-8 if index & 1 else 7) & 15, 4)
    payload = bytearray((len(bits) + 7) // 8)
    for at, value in enumerate(bits):
        payload[at // 8] |= value << (at % 8)
    return struct.pack('<4sBBHIHHHHH', b'L4HY', 5, profile | (128 if extras else 0),
                       8000, samples, 8192, 11469, 320, 160, len(payload)) + payload


class Sram512ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        cls.harness = cls.folder / 'profile.cpp'
        cls.harness.write_text(HARNESS)
        cls.executables = {}
        cls.base = ['-O2', '-std=c++11', '-DLPX4_ENABLE_ASM=0', '-I' + str(ROOT / 'src')]
        cls.compact = ['-DLPX4_ENABLE_SPEECH=1', '-DLPX4_ENABLE_SPEECH_COMPACT=1', '-DLPX4_COMPACT_ONLY=1']
        for segments in (1, 2, 4):
            for variant in ('default', 'standard', 'flag', 'header'):
                flags = [] if variant == 'header' else list(cls.compact)
                if variant == 'standard':
                    flags += ['-DLPX4_MEMORY_PROFILE=LPX4_MEMORY_PROFILE_STANDARD']
                elif variant == 'flag':
                    flags += ['-DLPX4_MEMORY_PROFILE=LPX4_MEMORY_PROFILE_SRAM512']
                elif variant == 'header':
                    flags += ['-include', str(ROOT / 'profiles/Lpx4Sram512.h')]
                exe = cls.folder / f'{variant}-{segments}'
                # Copy flags above: never accumulate settings across builds.
                subprocess.run([*CXX, *cls.base, *flags, f'-DLPX3_LPC_SEGMENTS={segments}',
                                str(cls.harness), '-o', str(exe)],
                               check=True, capture_output=True)
                cls.executables[segments, variant] = exe

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def compare(self, blob):
        source = self.folder / 'input.lpx'
        source.write_bytes(blob)
        for segments in (1, 2, 4):
            expected = None
            for variant in ('default', 'standard', 'flag', 'header'):
                run = subprocess.run([str(self.executables[segments, variant]), str(source)],
                                     check=True, capture_output=True)
                if expected is None:
                    expected = run.stdout
                self.assertEqual(run.stdout, expected, (segments, variant))
            self.assertEqual(len(expected), 3 * int.from_bytes(blob[8:12], 'little'))

    def test_pcm_pwm_partial_wrap_pitch_extremes_copy_and_reset(self):
        lengths = (1, 19, 20, 39, 40, 144, 145, 146, 159, 160, 180, 200, 220, 240,
                   254, 255, 256, 257, 280, 289, 319, 320, 321, 500, 641, 1280)
        for profile in (4, 6):
            for lag in (18, 145):
                for count in lengths:
                    self.compare(fixture(profile, count, lag))
            for style in ('static', 'clusters'):
                for extras in (False, True):
                    self.compare(fixture(profile, 1280, 145, style, extras))

    def test_workspace_preserves_live_history_at_every_cursor(self):
        source = self.folder / 'workspace.lpx'
        source.write_bytes(fixture(6, 641, 145, 'clusters'))
        for segments in (1, 2, 4):
            for variant in ('flag', 'header'):
                subprocess.run([str(self.executables[segments, variant]), str(source), '--workspace'],
                               check=True, capture_output=True)

    def test_layout_and_compile_guards(self):
        for segments in (1, 2, 4):
            sizes = {variant: int(subprocess.check_output([str(self.executables[segments, variant]), '--size']))
                     for variant in ('default', 'standard', 'flag', 'header')}
            self.assertEqual(sizes['default'], sizes['standard'])
            self.assertEqual(sizes['flag'], sizes['header'])
            self.assertEqual(sizes['standard'] - sizes['flag'], 96)
        source = self.folder / 'guard.cpp'
        source.write_text('#include "Lpx4HybridCore.h"\nint main(){}\n')
        for flags in ([*self.compact, '-DLPX4_MEMORY_PROFILE=-1'],
                      [*self.compact, '-DLPX4_MEMORY_PROFILE=2'],
                      ['-DLPX4_MEMORY_PROFILE=1'],
                      ['-DLPX4_ENABLE_SPEECH=1', '-DLPX4_ENABLE_SPEECH_COMPACT=1', '-DLPX4_MEMORY_PROFILE=1'],
                      ['-include', str(ROOT / 'profiles/Lpx4Sram512.h'), '-DLPX4_COMPACT_ONLY=0'],
                      ['-include', str(ROOT / 'profiles/Lpx4Sram512.h'), '-DLPX4_MEMORY_PROFILE=0']):
            run = subprocess.run([*CXX, *self.base, *flags, '-fsyntax-only', str(source)], capture_output=True)
            self.assertNotEqual(run.returncode, 0, flags)

    @unittest.skipUnless(os.environ.get('LPX4_SRAM512_FIXTURES'), 'optional local streams were not supplied')
    def test_optional_local_streams(self):
        for path in json.loads(os.environ['LPX4_SRAM512_FIXTURES']):
            self.compare(Path(path).read_bytes())


if __name__ == '__main__':
    unittest.main()
