/* Exact NB1 vocoder mean; original two-product C fallback remains selectable. */
#ifndef MICROMUSIC_SPEEX_LOWRATE_MEAN_H
#define MICROMUSIC_SPEEX_LOWRATE_MEAN_H
#include "speex_platform.h"

static SPEEX_NB3_ALWAYS_INLINE int16_t speex_low_mean_c(int16_t old,int16_t value)
{
    return (int16_t)(((int32_t)26214*old+(int32_t)6554*value+16384)>>15);
}

#if SPEEX_NB3_USE_AVR_ASM
int16_t speex_low_mean_avr(int16_t old,int16_t value);
#define speex_low_mean speex_low_mean_avr
#else
#define speex_low_mean speex_low_mean_c
#endif
#endif
