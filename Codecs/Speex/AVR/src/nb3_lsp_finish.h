/* Private order-ten polynomial output: p/q are six-word symmetric halves,
 * p[0]==q[0]==2^20. Inputs and the ten-word output are disjoint.
 * Keep modulo-32 arithmetic and independent rounding/saturation of each
 * coefficient; never round the shared sum or difference first. */
#ifndef MICROMUSIC_NB3_LSP_FINISH_H
#define MICROMUSIC_NB3_LSP_FINISH_H
#include "speex_platform.h"

static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_lsp_finish10_c(
    const int32_t *restrict p,const int32_t *restrict q,int16_t *restrict ak)
{
    for(unsigned j=1;j<=5;j++){
        int32_t sum=p[j]+p[j-1],diff=q[j]-q[j-1];
        int32_t a=(sum+diff+128)>>8,b=(sum-diff+128)>>8;
        if(a< -32767)a=-32767;if(a>32767)a=32767;
        if(b< -32767)b=-32767;if(b>32767)b=32767;
        ak[j-1]=(int16_t)a;ak[10-j]=(int16_t)b;
    }
}
#if SPEEX_NB3_USE_AVR_ASM
extern void speex_avr_lsp_finish10(const int32_t *,const int32_t *,int16_t *);
#endif
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_lsp_finish10(
    const int32_t *restrict p,const int32_t *restrict q,int16_t *restrict ak)
{
#if SPEEX_NB3_USE_AVR_ASM
    speex_avr_lsp_finish10(p,q,ak);
#else
    speex_nb3_lsp_finish10_c(p,q,ak);
#endif
}
#endif
