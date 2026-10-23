/* Portable bounded NB3 arithmetic; equivalent to the upstream fixed-point
 * expressions, without assuming a native byte order or using CPU intrinsics. */
#ifndef MICROMUSIC_NB3_C_MATH_H
#define MICROMUSIC_NB3_C_MATH_H
#include <stdint.h>
#include "speex_platform.h"

/* NB3 scale is positive and <=120988612: high<=29538, low<=4095.
 * MULT16_32_Q14(4*shape,scale) == floor(shape*scale/4096). The low
 * product is in [-524160,520065], so its >>8 fits signed16. The full
 * quotient has magnitude <2^22; aligning it by a byte fits signed32. */
static SPEEX_NB3_ALWAYS_INLINE int32_t speex_nb3_shape_scale_c(int8_t shape,
                                                           int16_t high,int16_t low)
{
    int32_t product=(int32_t)shape*low;
    int16_t fraction=(int16_t)(product>>8)>>4;
    int32_t quotient=(int32_t)shape*high+fraction;
    return (int32_t)((uint32_t)quotient<<8)>>1;
}
#endif
