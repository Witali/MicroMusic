/* Exact bounded HB1 gain and LPC-response divisions. Original PDIV32
 * rounding is preserved; neither helper is a general signed-divide API. */
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

/* LPC responses after the caller's positivity checks: low 1..335949,
 * high 1..270414. Preserve PDIV32's signed16 divisor cast before rounding.
 * These bounds follow from ten/eight arbitrary signed16 LPC coefficients. */
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_wb_ratio_div_c(int32_t low,int32_t high)
{
    int32_t q=(low*128+((int16_t)high>>1))/high;
    return q>32767?32767:q< -32767? -32767:(int16_t)q;
}

#if SPEEX_NB3_USE_AVR_ASM
/* Private bounded numerator: low*128 + ((int16_t)high>>1). */
int16_t speex_wb_ratio_div_avr(int32_t,int32_t);
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_wb_ratio_div(int32_t low,int32_t high)
{return speex_wb_ratio_div_avr(low*128+((int16_t)high>>1),high);}
#else
#define speex_wb_ratio_div speex_wb_ratio_div_c
#endif
#endif
