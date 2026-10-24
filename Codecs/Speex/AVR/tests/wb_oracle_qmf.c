/* Independent full-frame equation for the compact profile's final filter.
 * All NB/HB decoding, excitation, delay and LPC in the oracle are untouched
 * Xiph 1.2.1. Only qmf_synth calls in the disposable sb_celp.c are redirected.
 * Raw low/high histories and full-frame temporaries intentionally differ
 * from the AVR mirrored half-sum/difference streaming implementation. */
#include "wb_oracle_qmf.h"
#include <assert.h>
#include <stdint.h>
void speex_wb_reference_qmf(const spx_word16_t *low,const spx_word16_t *high,
    const spx_word16_t *a,spx_word16_t *out,int n,int m,
    spx_word16_t *low_mem,spx_word16_t *high_mem,char *stack)
{
    static const int h[16]={-4,-10,7,15,-14,-26,37,123,123,37,-26,-14,15,7,-10,-4};
    int16_t copy[320];int i,k;
    (void)a;(void)stack;assert(n==320 && m==64);
    for(i=0;i<160;i++){copy[i]=low[i];copy[160+i]=high[i];}
    for(i=0;i<160;i++) {
        int32_t even=0,odd=0;
        low_mem[i&7]=copy[i];high_mem[i&7]=copy[160+i];
        for(k=0;k<8;k++) {
            int index=(i-k)&7;
            int32_t l=low_mem[index],r=high_mem[index];
            even+=h[2*k]*((l-r)>>1);odd+=h[2*k+1]*((l+r)>>1);
        }
        even=(even+32)>>6;odd=(odd+32)>>6;
        out[2*i]=even>32767?32767:even< -32767?-32767:(int16_t)even;
        out[2*i+1]=odd>32767?32767:odd< -32767?-32767:(int16_t)odd;
    }
}
