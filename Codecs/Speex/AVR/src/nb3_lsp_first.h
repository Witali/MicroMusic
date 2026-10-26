/* Exact first two-root polynomial constructor, full signed16 a/b domain.
 * Only p[1] and p[2] are written; p[0] and all other memory stay unchanged.
 * The caller initializes p0=2^20 for the Speex recurrence. */
#ifndef MICROMUSIC_NB3_LSP_FIRST_H
#define MICROMUSIC_NB3_LSP_FIRST_H
#include "speex_platform.h"

/* Explicit portable C remains selectable on AVR. The negated root sum can
 * need 18 signed bits; its byte-aligned product still fits signed32. */
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_lsp_first_c(int32_t *p,int16_t a,int16_t b)
{
    p[1]=((int32_t)((uint32_t)(-((int32_t)a+b))<<8))>>2;
    p[2]=((int32_t)a*b+536871167)>>8;
}
#if SPEEX_NB3_USE_AVR_ASM
extern void speex_avr_lsp_first(int32_t *,int16_t,int16_t);
#endif
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_lsp_first(int32_t *p,int16_t a,int16_t b)
{
#if SPEEX_NB3_USE_AVR_ASM
    speex_avr_lsp_first(p,a,b);
#else
    speex_nb3_lsp_first_c(p,a,b);
#endif
}
#endif
