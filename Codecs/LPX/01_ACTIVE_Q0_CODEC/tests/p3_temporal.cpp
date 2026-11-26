#include "LpxSpectrumQuantizer.h"
#include <algorithm>
#include <cassert>
#include <iostream>
#include <random>

int main() {
    int previous[10], current[10];
    for (int k=0;k<10;++k) { previous[k]=k+2; current[k]=k+4; }
    lpxQuantizeSpectrum(current,previous,3);
    for (int k=0;k<10;++k)
        assert(current[k]==k+(LPX_ENCODER_P3_TEMPORAL_DEADZONE==2?2:4));
    // A sequence of legal one-cell spectral changes must not become a plateau.
    int changed=0;
    for (int step=1;step<=4;++step) {
        for (int k=0;k<10;++k)current[k]=k+2+2*step;
        lpxQuantizeSpectrum(current,previous,3);
        changed+=!std::equal(current,current+10,previous);
        std::copy(current,current+10,previous);
    }
    assert(changed==(LPX_ENCODER_P3_TEMPORAL_DEADZONE==2?2:4));
    std::mt19937 generator(20261126);
    for(int trial=0;trial<10000;++trial) {
        int values[32];for(int k=0;k<32;++k)values[k]=k;
        std::shuffle(values,values+32,generator);std::sort(values,values+10);
        std::copy(values,values+10,current);
        lpxQuantizeSpectrum(current,nullptr,3);
        for(int k=0;k<10;++k) {
            assert(current[k]>=0&&current[k]<32);
            assert(!k||current[k]>current[k-1]);
            assert(((current[k]-k)&1)==0);
        }
        std::copy(current,current+10,previous);
        lpxQuantizeSpectrum(current,previous,3);
        assert(std::equal(current,current+10,previous));
        for(int level:{0,4,6,8}) {
            std::copy(values,values+10,current);
            lpxQuantizeSpectrum(current,previous,level);
            assert(std::equal(current,current+10,values));
        }
    }
    std::cout<<"PASS: spectral changes, 10000 ordered vectors, idempotence, other levels; deadzone="<<LPX_ENCODER_P3_TEMPORAL_DEADZONE<<'\n';
}
