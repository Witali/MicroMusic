/* Restricted lossless NB3 pitch, adapted from Xiph 1.2.1 pitch_unquant_3tap.
 * Copyright (C) 2002-2006 Jean-Marc Valin; vendor/speex-1.2.1/COPYING.
 * The gain table+32 fits signed8; its maximum L1 norm is 147. Every prefix
 * sum is bounded by 147*32768=4816896 (<2^23). Defer the common *128 to
 * innovation, retaining exact products/sums in a 120-byte signed24 buffer. */
#ifndef MICROMUSIC_PITCH24_H
#define MICROMUSIC_PITCH24_H
#include <stdint.h>
#include <string.h>
#include "speex/speex_bits.h"
#include "speex_platform.h"
#include "avr_tables.h"
#include "packed24.h"
extern const signed char gain_cdbk_lbr[];
#if SPEEX_NB3_USE_AVR_ASM
extern void speex_avr_pitch_add24(uint8_t *,const int16_t *,int8_t,uint8_t,uint8_t);
#define PITCH_ADD24 speex_avr_pitch_add24
#else
static SPEEX_NB3_HOT SPEEX_NB3_NOINLINE void speex_nb3_pitch_add24_c(uint8_t *out,
    const int16_t *in,int8_t gain,uint8_t count,uint8_t accumulate)
{
    if (!gain) {
        if (!accumulate) memset(out,0,3*(unsigned)count);
        return;
    }
    while (count--) {
        int32_t value=(int32_t)gain * *in++;
        if (accumulate) value+=speex_nb3_read24(out);
        speex_nb3_write24(out,value);
        out+=3;
    }
}
#define PITCH_ADD24 speex_nb3_pitch_add24_c
#endif
static SPEEX_NB3_NOINLINE void speex_nb3_pitch24(const int16_t *exc,
                                               uint8_t *out,SpeexBits *bits)
{
    unsigned pitch=speex_bits_unpack_unsigned(bits,7)+17;
    unsigned index=speex_bits_unpack_unsigned(bits,5)*4;
    uint8_t tap;
    for (tap=0;tap<3;tap++) {
        unsigned pp=pitch+1-tap;
        uint8_t first=(uint8_t)(pp<40?pp:40);
        uint8_t end=(uint8_t)(pp+pitch<40?pp+pitch:40);
        int8_t gain=(int8_t)(32+AVR_READ_I8(gain_cdbk_lbr+index+2-tap));
        PITCH_ADD24(out,exc-pp,gain,first,tap!=0);
        if (end!=first)
            PITCH_ADD24(out+3*first,exc+first-pp-pitch,gain,end-first,tap!=0);
        if (!tap) memset(out+3*end,0,3*(40-end));
    }
}
#undef PITCH_ADD24
#endif
