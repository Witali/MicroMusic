#include "Lpx4FileGain.h"
extern "C" int lpx_file_gain_selftest() {
    int checks=0;
    const int16_t samples[]={-16384,-14003,-1,0,1,14003,16384};
    for(int gain=0;gain<=65535;++gain)for(int16_t sample:samples) {
        if(lpx4FileGainQ14Reference(sample,gain)!=lpx4FileGainQ14Unsigned(sample,gain))return -1;
        ++checks;
    }
    const uint16_t gains[]={0,1,256,2048,4096,9851,10439,65535};
    for(int sample=-16384;sample<=16384;++sample)for(uint16_t gain:gains) {
        if(lpx4FileGainQ14Reference(sample,gain)!=lpx4FileGainQ14Unsigned(sample,gain))return -2;
        ++checks;
    }
    return checks;
}
