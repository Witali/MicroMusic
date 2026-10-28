"""Host-only streaming durations versus independent full-history statistics."""
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <vector>
#include "profile_durations.h"
int main(){
 LpxProfileDurations state;lpx_profile_durations_init(&state);
 std::vector<uint64_t> prefix(1,0);uint64_t maxima[3]={0,0,0},maximum=0;
 const unsigned widths[3]={40,80,160};uint32_t random=1;
 for(unsigned index=0;index<300000;++index){
  random=random*1664525U+1013904223U;
  uint64_t value=index<64000?(random&1023):index<128000?100000+(random&4095):UINT64_C(0x100000000)+(random&65535);
  prefix.push_back(prefix.back()+value);if(value>maximum)maximum=value;
  if(!lpx_profile_durations_push(&state,value))return 1;
  if(state.count!=index+1 || state.total!=prefix.back() || state.maximum!=maximum)return 2;
  for(unsigned k=0;k<3;++k){
   unsigned count=index+1;
   uint64_t sum=prefix[count]-prefix[count>widths[k]?count-widths[k]:0];
   if(count>=widths[k] && sum>maxima[k])maxima[k]=sum;
   if(state.sums[k]!=sum || state.maxima[k]!=maxima[k])return 3;
   // Independent old backward-window calculation around all boundaries.
   if(count<400 || count==64000 || count==64001 || count==281632){
    uint64_t oldMax=0;
    for(unsigned end=0;end<count;++end){
     uint64_t oldSum=0;
     for(unsigned width=1;width<=widths[k] && width<=end+1;++width)oldSum+=prefix[end+2-width]-prefix[end+1-width];
     if(end+1>=widths[k] && oldSum>oldMax)oldMax=oldSum;
    }
    if(oldMax!=state.maxima[k])return 4;
   }
  }
 }
 lpx_profile_durations_init(&state);
 if(state.count || state.total || state.maximum || state.maxima[0] || state.maxima[1] || state.maxima[2])return 5;
 if(!lpx_profile_durations_push(&state,UINT64_MAX))return 6;
 LpxProfileDurations before=state;
 if(lpx_profile_durations_push(&state,1) || memcmp(&before,&state,sizeof(state)))return 7;
 state.count=UINT64_MAX;before=state;
 if(lpx_profile_durations_push(&state,0) || memcmp(&before,&state,sizeof(state)))return 8;
 puts("300000 full-history streaming duration cases exact; overflow guarded");
}
'''


class ProfileDurationTests(unittest.TestCase):
    def test_rolling_totals_and_window_maxima_include_long_tail(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'durations.cpp';source.write_text(SOURCE,encoding='utf-8')
            executable=Path(td)/'durations.exe'
            subprocess.run(['g++','-O2','-std=c++11','-I'+str(ROOT.parent/'validation/atmega328p'),
                            str(source),'-o',str(executable)],check=True,capture_output=True)
            self.assertEqual(subprocess.check_output([str(executable)],text=True).strip(),
                             '300000 full-history streaming duration cases exact; overflow guarded')


if __name__=='__main__':unittest.main()
