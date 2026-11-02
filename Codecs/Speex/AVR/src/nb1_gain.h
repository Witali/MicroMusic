/* Exact finite control map for Xiph Speex NB1 vocoder excitation.
 * Original project derivation from the pinned Xiph 1.2.1 formulas (BSD). */
#ifndef MICROMUSIC_SPEEX_NB1_GAIN_H
#define MICROMUSIC_SPEEX_NB1_GAIN_H
#include "forced_math.h"
#include "avr_tables.h"

/* All sixteen coefficient codes, followed by rounded Q14(1.5*(c-13))
 * and the original 0..64 clamp. This is exact, not a quantizer change. */
static const int8_t speex_nb1_gain_table[16] AVR_TABLE=
    {0,0,0,0,6,12,20,26,32,38,45,51,57,63,64,64};
static SPEEX_NB3_ALWAYS_INLINE uint8_t speex_nb1_gain_table_c(uint8_t code)
{return (uint8_t)AVR_READ_I8(speex_nb1_gain_table+code);}
/* The table already satisfies this bound; expose it to the compiler too. */
static SPEEX_NB3_ALWAYS_INLINE uint8_t speex_nb1_gain_bounded_table_c(uint8_t code)
{
    uint8_t g=speex_nb1_gain_table_c(code);
    return g>64?64:g;
}
/* Measured AVR-GCC caller recipes: WB uses the direct read; standalone NB
 * benefits from the explicit bound in subsequent arithmetic. Both are C. */
static SPEEX_NB3_ALWAYS_INLINE uint8_t speex_nb1_gain_selected_c(uint8_t code)
{
#if SPEEX_ENABLE_WB1
    return speex_nb1_gain_table_c(code);
#else
    return speex_nb1_gain_bounded_table_c(code);
#endif
}

/* Explicit portable arithmetic reference, also callable on AVR. Coefficient
 * code15 still produces64; this caller has no NB8-style coefficient clamp. */
static SPEEX_NB3_ALWAYS_INLINE uint8_t speex_nb1_gain_c(uint8_t code)
{
    int16_t coefficient=speex_forced_coefficient_c(code);
    int16_t g=(3*(coefficient-13)+1)>>1;
    if(g<0)g=0;if(g>64)g=64;
    return (uint8_t)g;
}
#endif
