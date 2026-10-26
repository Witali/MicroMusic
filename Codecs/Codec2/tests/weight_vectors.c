/* Deterministic fixed-spectrum cross-ABI vectors; generated files stay in build/. */
#include "fixed_weight.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
static uint32_t seed=1;
static float next(void){seed=seed*UINT32_C(1664525)+UINT32_C(1013904223);return ((int32_t)(seed>>8)-8388608)/65536.0f;}
int main(int argc,char **argv){
    assert(argc==3);FILE *input=fopen(argv[1],"wb"),*expected=fopen(argv[2],"wb");assert(input&&expected);
    for(unsigned trial=0;trial<512;++trial){
        float a[11],gamma=1,scale=ldexpf(1,(int)(trial%33)-16);compact_complex output[256];codec2_weight state;
        for(unsigned i=0;i<11;++i){a[i]=(trial==0?0:trial<=11?(float)(i==trial-1):i==0?1:next())*gamma*scale;gamma*=.5f;}
        codec2_weight_init(&state,a);output[0]=codec2_weight_dc(&state);
        for(unsigned k=1;k<=128;++k){compact_complex positive,negative;codec2_weight_pair(&state,k,&positive,&negative);output[k]=positive;output[256-k]=negative;}
        assert(fwrite(a,sizeof(a),1,input)==1);assert(fwrite(output,sizeof(output),1,expected)==1);
    }
    assert(fclose(input)==0&&fclose(expected)==0);return 0;
}
