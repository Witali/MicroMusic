/* Exact lifetime optimization checked against the frozen wide integer graph. */
#define codec2_analysis_forward codec2_analysis_reference_forward
#include "../src/faithful_analysis.c"
#include "../src/compact_analysis_helpers.inc"
#include <stdio.h>
static uint32_t seed=1;
static float next(void){seed=seed*UINT32_C(1664525)+UINT32_C(1013904223);return ((int32_t)(seed>>8)-8388608)/65536.0f;}
int main(void){
    const float polynomial[11]={1,-10,45,-120,210,-252,210,-120,45,-10,1};
    for(unsigned trial=0;trial<256;++trial){
        float a[11],total=0,scale=ldexpf(1,(int)(trial%33)-16);faithful_context state;
        for(unsigned i=0;i<11;++i){float value=trial==0?0:trial<=11?(float)(i==trial-1):trial==12?polynomial[i]:trial==13?((i&1)?-polynomial[i]:polynomial[i]):i==0?1:next();a[i]=value*scale;total+=fabsf(a[i]);}
        int exponent;frexpf(total,&exponent);state.exponent=exponent-(CODEC2_FAITHFUL_BITS-3);
        for(unsigned i=0;i<11;++i){uint32_t bits;memcpy(&bits,&a[i],4);state.a[i]=from_bits(bits,state.exponent);}
        for(unsigned k=0;k<256;++k){faithful_complex original=spectrum(&state,k),compact=compact_spectrum(&state,k);assert(original.r==compact.r&&original.i==compact.i);}
    }
    puts("PASS: compact and original integer spectrum graphs agree on 65536 zero/basis/cancellation/random complex outputs");return 0;
}
