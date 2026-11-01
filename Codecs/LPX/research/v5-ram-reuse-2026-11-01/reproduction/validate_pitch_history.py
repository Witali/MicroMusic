"""Exact bounded v5 pitch history; fixtures need no encoder or audio packages."""
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(os.environ['LPX4_HISTORY_SOURCE']).resolve()
FLAGS = ['-DLPX4_ENABLE_SPEECH=1', '-DLPX4_ENABLE_SPEECH_COMPACT=1',
         '-DLPX4_COMPACT_ONLY=1', '-DLPX4_ENABLE_ASM=0']

HARNESS = r'''
#include <stdint.h>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include <cstdio>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
#include "Lpx4HybridCore.h"
int main(int argc,char** argv){
#ifdef _WIN32
 if(_setmode(_fileno(stdout),_O_BINARY)==-1)return 12;
#endif
 if(argc!=2)return 1;
 std::ifstream in(argv[1],std::ios::binary);
 std::vector<uint8_t> blob((std::istreambuf_iterator<char>(in)),{});
 Lpx4HybridCore pcm,pwm;
 if(!pcm.begin(blob.data(),blob.size())||!pwm.begin(blob.data(),blob.size()))return 2;
 std::vector<int16_t> expected;int16_t value;uint8_t duty;
 while(pcm.nextS16(value)){
  if(!pwm.next(duty))return 3;
  expected.push_back(value);
  std::cout.put((uint8_t)value);std::cout.put((uint16_t)value>>8);std::cout.put(duty);
 }
 if(pwm.next(duty)||pcm.error()||pwm.error()||expected.size()!=pcm.samples())return 4;
 const unsigned cuts[]={1,18,39,40,144,145,146,159,160,254,255,256,257,509};
 for(unsigned cut:cuts){
  if(cut>expected.size())continue;
  Lpx4HybridCore original;if(!original.begin(blob.data(),blob.size()))return 5;
  for(unsigned i=0;i<cut;i++)if(!original.nextS16(value))return 6;
  Lpx4HybridCore copied=original,assigned;assigned=original;
  original.begin(0,0);
  for(Lpx4HybridCore* state:{&copied,&assigned}){
   for(unsigned i=cut;i<expected.size();i++)
    if(!state->nextS16(value)||value!=expected[i]||state->produced()!=i+1)return 7;
   if(state->nextS16(value)||!state->finished()||state->error())return 8;
   if(!state->begin(blob.data(),blob.size()))return 9;
   for(int16_t sample:expected)if(!state->nextS16(value)||value!=sample)return 10;
   if(state->nextS16(value)||state->error())return 11;
  }
 }
 return 0;
}
'''


def fixture(profile, samples, lag):
    """Explicit legal gap/repeat spectra, endpoint lags and optional collisions."""
    bits = []

    def put(value, width):
        bits.extend((value >> i) & 1 for i in range(width))

    for frame in range((samples + 319) // 320):
        # A legal absolute gap spectrum. Alternate two vectors so interpolation
        # and conversion run alongside nonzero pitch, filter state and wrapping.
        put(1, 1)
        put(0, 1)
        k = 1 if profile == 4 else 2
        for gap in [1 + frame % 2] + [1] * 9:
            put(0, gap >> k)
            put(1, 1)
            put(gap & ((1 << k) - 1), k)
        for half in range(2):
            put(26 + (frame + half) % 6, 5)
            put(lag - 18, 7)
            put(7, 3)
            for group in range(4):
                at = frame * 8 + half * 4 + group
                if profile == 4:
                    for index in (at % 16, (at * 7 + 3) % 16):
                        put(index, 4)
                        put((at + index) % 3 == 0, 1)
                else:
                    combo = (at * 3) % 20 + 20 * ((at * 7 + 19) % 20)
                    put(combo & 255, 8)
                    put(combo >> 8, 1)
                    put((at % 16), 4)
                    put((15 - at % 16), 4)
                put(1, 1)
                put((0, 19, 20, 39)[at % 4], 6)
                put(7 if at % 2 else 8, 4)
    payload = bytes(sum(bit << j for j, bit in enumerate(bits[i:i + 8]))
                    for i in range(0, len(bits), 8))
    return struct.pack('<4sBBHIHHHHH', b'L4HY', 5, profile | 128, 8000,
                       samples, 8192, 4096, 320, 160, len(payload)) + payload


class PitchHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.folder = Path(cls.temporary.name)
        source = cls.folder / 'history.cpp'
        source.write_text(HARNESS)
        cls.executables = {}
        for size in (None, 145, 160, 255, 256):
            exe = cls.folder / ('history-' + str(size) + '.exe')
            flags = [] if size is None else ['-DLPX4_PITCH_HISTORY_SIZE=' + str(size)]
            subprocess.run(['g++', '-O2', '-std=c++11', *FLAGS, *flags,
                            '-I' + str(ROOT / 'src'), str(source),
                            str(ROOT / 'src/Lpx4HybridCore.cpp'), '-o', str(exe)],
                           check=True, capture_output=True)
            cls.executables[size] = exe

    def compare(self, blob):
        path = self.folder / 'fixture.l4hy'
        path.write_bytes(blob)
        outputs = [subprocess.run([str(exe), str(path)], check=True,
                                 capture_output=True).stdout
                   for exe in self.executables.values()]
        self.assertEqual(len(outputs[0]), int.from_bytes(blob[8:12], 'little') * 3)
        for output in outputs[1:]:
            self.assertEqual(output, outputs[0])

    def test_endpoint_lags_wrap_boundaries_tails_copy_and_reset(self):
        for profile in (4, 6):
            for lag in (18, 145):
                for samples in (1, 19, 20, 39, 40, 144, 145, 146, 159, 160,
                                254, 255, 256, 257, 289, 319, 320, 321, 641, 1280):
                    with self.subTest(profile=profile, lag=lag, samples=samples):
                        self.compare(fixture(profile, samples, lag))

    def test_invalid_lengths_and_legacy_layout_are_compile_errors(self):
        source = self.folder / 'invalid.cpp'
        source.write_text('#include "Lpx4HybridCore.h"\n')
        for size, compact in ((0, 1), (144, 1), (257, 1), (145, 0)):
            flags = [f for f in FLAGS if not f.startswith('-DLPX4_COMPACT_ONLY=')]
            result = subprocess.run(['g++', '-std=c++11', '-fsyntax-only', *flags,
                                     '-DLPX4_COMPACT_ONLY=' + str(compact),
                                     '-DLPX4_PITCH_HISTORY_SIZE=' + str(size),
                                     '-I' + str(ROOT / 'src'), str(source)],
                                    capture_output=True)
            self.assertNotEqual(result.returncode, 0, (size, compact))

    def test_optional_private_input_streams(self):
        paths = json.loads(os.environ.get('LPX4_PITCH_HISTORY_FIXTURES', '[]'))
        if not paths:
            self.skipTest('No private playback fixtures supplied')
        for path in paths:
            self.compare(Path(path).read_bytes())


if __name__ == '__main__':
    unittest.main()
