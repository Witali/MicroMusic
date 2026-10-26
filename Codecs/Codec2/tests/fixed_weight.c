#include "fixed_weight.h"
#include "kiss_fftr.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint32_t seed=1;
static float next(void){seed=seed*UINT32_C(1664525)+UINT32_C(1013904223);return ((int32_t)(seed>>8)-8388608)/65536.0f;}
int main(void){
    kiss_fftr_cfg fft=kiss_fftr_alloc(512,0,NULL,NULL);assert(fft);double signal=0,noise=0,maximum=0;
    for(unsigned trial=0;trial<512;++trial){
        float a[11],input[512]={0};kiss_fft_cpx expected[257];compact_complex actual[256];
        float gamma=1;for(unsigned i=0;i<11;++i){a[i]=(trial<11?(float)(i==trial):i==0?1:next())*gamma;gamma*=.5f;}
        memcpy(input,a,sizeof(a));kiss_fftr(fft,input,expected);codec2_weight state;codec2_weight_init(&state,a);actual[0]=codec2_weight_dc(&state);
        for(unsigned k=1;k<=128;++k){compact_complex positive,negative;codec2_weight_pair(&state,k,&positive,&negative);actual[k]=positive;actual[256-k]=negative;}
        for(unsigned i=0;i<256;++i){double dr=actual[i].r-expected[i].r,di=actual[i].i-expected[i].i;signal+=(double)expected[i].r*expected[i].r+(double)expected[i].i*expected[i].i;noise+=dr*dr+di*di;maximum=fmax(maximum,fmax(fabs(dr),fabs(di)));}
    }
    kiss_fftr_free(fft);printf("{\"vectors\":512,\"bins_per_vector\":256,\"snr_db\":%.12g,\"maximum_absolute_error\":%.12g}\n",10*log10(signal/noise),maximum);return 0;
}
