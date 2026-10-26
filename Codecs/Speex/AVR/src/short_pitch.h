#include "nb3_indices.h"
/* Exact short-pitch excitation for Xiph NB3/NB4, pitch 17..40.
 * Choose contiguous history ranges before each inner loop. Four isolated
 * switch/tail samples keep the original three-tap source indices. Every
 * history read is completed before output is written. Xiph BSD provenance:
 * Copyright (C) 2002-2006 Jean-Marc Valin; vendor/speex-1.2.1/COPYING. */
#ifndef MICROMUSIC_NB3_SHORT_PITCH_H
#define MICROMUSIC_NB3_SHORT_PITCH_H
#include "speex/speex_bits.h"
#include "long_pitch.h"
#include "zero_innovation.h"
extern const signed char gain_cdbk_lbr[],exc_10_32_table[],exc_8_128_table[];
#if !SPEEX_NB3_USE_AVR_ASM
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_nb3_segment_finish_c(int32_t adaptive,
    int8_t shape,int16_t high,int16_t low)
{
    int32_t innovation=speex_nb3_shape_scale_c(shape,high,low);
    if(adaptive>2048000) adaptive=2048000;
    if(adaptive<-2048000) adaptive=-2048000;
    return speex_nb3_saturating_q14_c(
        (int32_t)(((uint32_t)adaptive<<8)+(uint32_t)innovation+8192));
}
#endif
#define SPEEX_SHORT_NAME speex_nb3_short_innovation
#define SPEEX_SHORT_VECTORS 4
#define SPEEX_SHORT_SIZE 10
#define SPEEX_SHORT_TABLE exc_10_32_table
#include "short_pitch_kernel.inc"
#undef SPEEX_SHORT_NAME
#undef SPEEX_SHORT_VECTORS
#undef SPEEX_SHORT_SIZE
#undef SPEEX_SHORT_TABLE
#if SPEEX_ENABLE_NB4
#define SPEEX_SHORT_NAME speex_nb4_short_innovation
#define SPEEX_SHORT_VECTORS 5
#define SPEEX_SHORT_SIZE 8
#define SPEEX_SHORT_TABLE exc_8_128_table
#include "short_pitch_kernel.inc"
#undef SPEEX_SHORT_NAME
#undef SPEEX_SHORT_VECTORS
#undef SPEEX_SHORT_SIZE
#undef SPEEX_SHORT_TABLE
#endif
#endif
