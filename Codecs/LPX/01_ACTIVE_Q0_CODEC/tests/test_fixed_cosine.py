"""Pinned P4 keeps every reachable cosine node and complete C decoder output."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_sram512_profile import CXX, ROOT, fixture


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
#include "Lpx4HybridCore.cpp"

#if LPX3_LPC_SEGMENTS != 4
// Frozen original generic half-wave table, before pinned-P4 compaction.
static const int16_t originalEven[65]={
 8192,8190,8182,8170,8153,8130,8103,8071,
 8035,7993,7946,7895,7839,7779,7713,7643,
 7568,7489,7405,7317,7225,7128,7027,6921,
 6811,6698,6580,6458,6333,6203,6070,5933,
 5793,5649,5501,5351,5197,5040,4880,4717,
 4551,4383,4212,4038,3862,3683,3503,3320,
 3135,2948,2760,2570,2378,2185,1990,1795,
 1598,1401,1202,1003,803,603,402,201,0
};
static_assert(sizeof(cosineEven)/sizeof(cosineEven[0])==TEST_COSINE_WORDS,
              "Only pinned SRAM512 P4 may retain33 half-grid nodes");
#endif

int main(int argc,char** argv){
#ifdef _WIN32
 if(_setmode(_fileno(stdout),_O_BINARY)==-1)return 1;
#endif
 if(argc!=2)return 2;
 if(!strcmp(argv[1],"--nodes")){
#if LPX3_LPC_SEGMENTS != 4
  unsigned checked=0;
  for(unsigned index=0;index<=128;index+=(TEST_COSINE_WORDS==33?2:1)){
   const bool negative=index>64;
   const int16_t value=originalEven[negative?128-index:index];
   if(cosineEvenNode((uint8_t)index)!=(negative?-value:value))return 3;
   ++checked;
  }
  printf("%u\n",checked);return 0;
#else
  return 4;
#endif
 }
 std::ifstream file(argv[1],std::ios::binary);
 std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(file)),{});
 Lpx4HybridCore pcm,pwm;
 if(!pcm.begin(bytes.data(),bytes.size())||!pwm.begin(bytes.data(),bytes.size()))return 5;
 unsigned count=0;int16_t sample;uint8_t duty;
 while(pcm.nextS16(sample)){
  if(!pwm.next(duty))return 6;
  const uint8_t result[]={(uint8_t)sample,(uint8_t)((uint16_t)sample>>8),duty};
  if(fwrite(result,1,sizeof(result),stdout)!=sizeof(result))return 7;
  ++count;
 }
 if(pwm.next(duty)||pcm.error()||pwm.error()||!pcm.finished()||!pwm.finished())return 8;
 if(count!=pcm.samples()||pcm.produced()!=count||pwm.produced()!=count)return 9;
 return 0;
}
'''


class FixedCosineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        source = cls.folder / 'fixed-cosine.cpp'
        source.write_text(HARNESS)
        cls.executables = {}
        for segments in (1, 2, 4):
            for memory, flags in ((0, None), (1, None), (0, 4), (0, 132),
                                  (1, 4), (1, 132), (1, 6), (1, 134)):
                words = 33 if memory == 1 and flags in (4, 132) else 65
                exe = cls.folder / f'cosine-{segments}-{memory}-{flags}'
                defines = [f'-DLPX3_LPC_SEGMENTS={segments}', f'-DLPX4_MEMORY_PROFILE={memory}',
                           f'-DTEST_COSINE_WORDS={words}']
                if flags is not None:
                    defines.append(f'-DLPX4_FIXED_SPEECH_FLAGS={flags}')
                subprocess.run([*CXX, '-O2', '-std=c++11', '-DLPX4_ENABLE_ASM=0',
                                '-DLPX4_ENABLE_SPEECH=1', '-DLPX4_ENABLE_SPEECH_COMPACT=1',
                                '-DLPX4_COMPACT_ONLY=1', '-I' + str(ROOT / 'src'),
                                *defines, str(source), '-o', str(exe)], check=True, capture_output=True)
                cls.executables[segments, memory, flags] = exe

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_every_reachable_even_node_and_full_table_controls(self):
        for (segments, memory, flags), exe in self.executables.items():
            if segments == 4:
                continue  # This path uses the unchanged full cosine interpolator.
            with self.subTest(segments=segments, memory=memory, flags=flags):
                actual = int(subprocess.check_output([str(exe), '--nodes']))
                self.assertEqual(actual, 65 if memory == 1 and flags in (4, 132) else 129)

    def test_complete_pcm_pwm_matches_dynamic_for_pitch_and_spectrum_extremes(self):
        stream = self.folder / 'synthetic.lpx'
        for segments in (1, 2, 4):
            for profile in (4, 6):
                for extras in (False, True):
                    flags = profile | (128 if extras else 0)
                    for lag in (18, 145):
                        for style in ('changing', 'clusters'):
                            with self.subTest(segments=segments, profile=profile, extras=extras,
                                              lag=lag, style=style):
                                stream.write_bytes(fixture(profile, 1280, lag, style, extras))
                                run = lambda memory, pin: subprocess.check_output([
                                    str(self.executables[segments, memory, pin]), str(stream)])
                                expected = run(0, None)
                                self.assertEqual(len(expected), 3 * 1280)
                                self.assertEqual(run(1, None), expected)
                                self.assertEqual(run(1, flags), expected)
                                if profile == 4:
                                    self.assertEqual(run(0, flags), expected)


if __name__ == '__main__':
    unittest.main()
