/* Paired sequential p then q stages. Arrays are disjoint and each addresses n+2 words;
 * p0/q0=2^20, p1/q1 divisible by 64, signed30 product inputs. */
#ifndef MICROMUSIC_NB3_LSP_PAIR_H
#define MICROMUSIC_NB3_LSP_PAIR_H
#include "nb3_lsp_stage.h"
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_lsp_pair_c(int32_t *p,int32_t *q,int16_t fp,int16_t fq,int n)
{speex_nb3_lsp_stage_c(p,fp,n);speex_nb3_lsp_stage_c(q,fq,n);}
#if SPEEX_NB3_USE_AVR_ASM
#define PAIR(n) \
extern void speex_avr_lsp_pair##n(int32_t *,int32_t *,int16_t,int16_t); \
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_lsp_pair##n(int32_t *p,int32_t *q,int16_t fp,int16_t fq) \
{speex_avr_lsp_pair##n(p,q,fp,fq);}
#else
#define PAIR(n) \
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_lsp_pair##n(int32_t *p,int32_t *q,int16_t fp,int16_t fq) \
{speex_nb3_lsp_pair_c(p,q,fp,fq,n);}
#endif
PAIR(2)
PAIR(3)
PAIR(4)
#undef PAIR
#endif
