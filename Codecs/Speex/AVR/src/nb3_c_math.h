/* Portable NB3 arithmetic; equivalent to the upstream fixed-point
 * expressions, without assuming a native byte order or using CPU intrinsics. */
#ifndef MICROMUSIC_NB3_C_MATH_H
#define MICROMUSIC_NB3_C_MATH_H
#include <stdint.h>
#include "speex_platform.h"

/* Exact generic Xiph MULT16_32_Q14, including the signed16 cast of b>>14.
 * The low product has magnitude <2^29, so its floor >>14 fits signed16.
 * Both required words are bits 14..29; unsigned alignment discards only
 * bits the original signed16 casts discard. No restriction on signed32 b. */
static SPEEX_NB3_ALWAYS_INLINE int32_t speex_nb3_mul16_32_q14_c(int16_t a,int32_t b)
{
    int16_t high=(int16_t)(((uint32_t)b<<2)>>16);
    int32_t low_product=(int32_t)a*(int16_t)(b&16383);
    int16_t low=(int16_t)(((uint32_t)low_product<<2)>>16);
    return (int32_t)a*high+low;
}

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
/* Zero adaptive sum, signed8 shape, 0<=scale<=121000000. The original
 * double floor and Q14 rounding reduce exactly to (shape*scale+2^18)>>19.
 * The result fits +/-29542, so neither wrap nor output saturation is active.
 * Each byte product plus floor carry fits signed16. The first three steps
 * divide the low 24-bit contribution by 65536; the fourth contributes an
 * exact multiple of 256. c+4 and d*32 fit signed16 for this bound. */
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_nb3_zero_shape_c(int8_t shape,
                                                            int32_t scale)
{
    int16_t a=(int16_t)shape*(uint8_t)scale;
    int16_t b=(int16_t)shape*(uint8_t)(scale>>8)+(a>>8);
    int16_t c=(int16_t)shape*(uint8_t)(scale>>16)+(b>>8);
    int16_t d=(int16_t)shape*(uint8_t)(scale>>24);
    return (int16_t)(((c+4)>>3)+d*32);
}
/* Saturate floor(rounded/16384) to +/-32767. Clamp before discarding
 * bits: every remaining result fits signed16, so retain only bits 14..29
 * with unsigned left alignment and a whole-word extraction. This also
 * preserves the original -32768 -> -32767 saturation for all signed32. */
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_nb3_saturating_q14_c(int32_t rounded)
{
    if (rounded>=536854528) return 32767;
    if (rounded<=-536854528) return -32767;
    return (int16_t)(((uint32_t)rounded<<2)>>16);
}
#endif
