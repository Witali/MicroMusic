/* Private symmetric polynomial stages: six int32 slots, p0=2^20,
 * p1 divisible by 64; product inputs satisfy -2^29 <= b < 2^29.
 * For actual signed16 cosine roots, the four construction stages bound
 * their largest product inputs by 2097152,6291457,20971523,73400331.
 * Stages 2..4 read p1 from at most four roots, |p1|<=8388608.
 * Use wrapping signed arithmetic and independent original Q14 floors. */
#ifndef MICROMUSIC_NB3_LSP_STAGE_H
#define MICROMUSIC_NB3_LSP_STAGE_H
#include "nb3_c_math.h"

/* Explicit C is always available on AVR, independently of the selector. */
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_lsp_stage_c(int32_t *p,int16_t f,int stage)
{
    p[stage+1]=2*p[stage-1]-speex_nb3_mul16_32_q14_c(f,p[stage]);
    for(int j=stage;j>=2;j--)
        p[j]=p[j]-speex_nb3_mul16_32_q14_c(f,p[j-1])+p[j-2];
    /* Unsigned shift is defined for negative f's bit pattern. Its signed
     * result is exactly f*64; on AVR GCC it avoids a slower multiply helper. */
    p[1]-=(int32_t)((uint32_t)(int32_t)f<<6);
}
#if SPEEX_NB3_USE_AVR_ASM
#define SPEEX_NB3_LSP_STAGE(n) \
extern void speex_avr_lsp_stage##n(int32_t *,int16_t); \
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_lsp_stage##n(int32_t *p,int16_t f) \
{speex_avr_lsp_stage##n(p,f);}
#else
#define SPEEX_NB3_LSP_STAGE(n) \
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_lsp_stage##n(int32_t *p,int16_t f) \
{speex_nb3_lsp_stage_c(p,f,n);}
#endif
SPEEX_NB3_LSP_STAGE(2)
SPEEX_NB3_LSP_STAGE(3)
SPEEX_NB3_LSP_STAGE(4)
#undef SPEEX_NB3_LSP_STAGE
#endif
