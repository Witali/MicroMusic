#define private public
#include "Lpx4HybridCore.cpp"
#include <stdio.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif

static uint32_t state=20261027UL;
static uint16_t nextLsf(){state=state*1664525UL+1013904223UL;return (uint16_t)(state>>22);}

int main(){
#ifdef _WIN32
    _setmode(_fileno(stdout),_O_BINARY);
#endif
    Lpx4HybridCore core;
    int16_t out[10];
    // Seeded extremes/random vectors and every interpolation anchor t=0..16.
    for(uint16_t trial=0;trial<2048;trial++){
        for(uint8_t i=0;i<10;i++){
            core.prev_[i]=trial<16?((trial&1)?1023:0):nextLsf();
            core.cur_[i]=trial<16?((trial&2)?1023:0):nextLsf();
            if(trial<16 && (trial&4)){core.prev_[i]=(i&1)?core.prev_[i]:1023-core.prev_[i];}
            if(trial<16 && (trial&8)){core.cur_[i]=(i&1)?core.cur_[i]:1023-core.cur_[i];}
        }
        for(uint8_t t=0;t<=16;t++){
            core.convertLsfAt(t,out);
            // Canonical little-endian words make the frozen digest host-independent.
            for(uint8_t i=0;i<10;i++){
                const uint16_t word=(uint16_t)out[i];
                if(putchar((uint8_t)word)==EOF || putchar((uint8_t)(word>>8))==EOF)return 1;
            }
        }
    }
    return 0;
}
