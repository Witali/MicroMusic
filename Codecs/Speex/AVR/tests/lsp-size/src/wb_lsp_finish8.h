/* Private order-eight half-polynomial finish: five words per input,
 * p[0]==q[0]==2^20. Inputs and eight-word output are disjoint.
 * Use wrapping signed32 arithmetic and separate rounding/saturation. */
#ifndef MICROMUSIC_WB_LSP_FINISH8_H
#define MICROMUSIC_WB_LSP_FINISH8_H
#include "speex_platform.h"
static SPEEX_NB3_ALWAYS_INLINE void speex_wb_lsp_finish8_c(
    const int32_t *restrict p,const int32_t *restrict q,int16_t *restrict ak)
{
    for(unsigned j=1;j<=4;j++) {
        int32_t sum=p[j]+p[j-1],diff=q[j]-q[j-1];
        int32_t a=(sum+diff+128)>>8,b=(sum-diff+128)>>8;
        if(a< -32767)a=-32767;if(a>32767)a=32767;
        if(b< -32767)b=-32767;if(b>32767)b=32767;
        ak[j-1]=(int16_t)a;ak[8-j]=(int16_t)b;
    }
}
#if SPEEX_NB3_USE_AVR_ASM
void speex_avr_lsp_finish8(const int32_t *,const int32_t *,int16_t *);
#endif
static SPEEX_NB3_ALWAYS_INLINE void speex_wb_lsp_finish8(
    const int32_t *restrict p,const int32_t *restrict q,int16_t *restrict ak)
{
#if SPEEX_NB3_USE_AVR_ASM
    speex_avr_lsp_finish8(p,q,ak);
#else
    speex_wb_lsp_finish8_c(p,q,ak);
#endif
}
#endif
