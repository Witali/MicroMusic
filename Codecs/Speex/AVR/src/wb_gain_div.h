/* HB1's second division only: table energy 0..904448, ratio 1..32767.
 * The original PDIV32 rounding is preserved. No general signed-divide API. */
#ifndef MICROMUSIC_SPEEX_WB_GAIN_DIV_H
#define MICROMUSIC_SPEEX_WB_GAIN_DIV_H
#include "speex_platform.h"

static SPEEX_NB3_ALWAYS_INLINE int32_t speex_wb_gain_div_c(int32_t energy,int16_t ratio)
{
    return (energy+(ratio>>1))/(int32_t)ratio;
}

#if SPEEX_NB3_USE_AVR_ASM
int32_t speex_wb_gain_div_avr(int32_t,int16_t);
#define speex_wb_gain_div speex_wb_gain_div_avr
#else
#define speex_wb_gain_div speex_wb_gain_div_c
#endif
#endif
