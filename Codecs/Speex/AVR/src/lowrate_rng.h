/* Exact modulo-2^32 Xiph noise LCG. Original project constant multiplier;
 * no random-sequence or fixed-point precision change. */
#ifndef MICROMUSIC_SPEEX_LOWRATE_RNG_H
#define MICROMUSIC_SPEEX_LOWRATE_RNG_H
#include "speex_platform.h"

static SPEEX_NB3_ALWAYS_INLINE uint32_t speex_low_rng_next_c(uint32_t value)
{
    return UINT32_C(1664525)*value+UINT32_C(1013904223);
}

static SPEEX_NB3_ALWAYS_INLINE uint32_t speex_low_rng_next(uint32_t value)
{
#if SPEEX_NB3_USE_AVR_ASM
    /* A = 0x0019660d = 13 + 102*256 + 25*65536. Reuse the
     * 13*x0/x1 products for 25*x0/x1, leaving seven MUL instructions.
     * 25*x0 <= 6375 fits the initial upper word. All later carries and
     * discarded high bits follow arithmetic modulo 2^32. Constants are
     * register inputs so the 40-sample caller can hoist their loads. */
    uint32_t result;
    __asm__(
        "clr r2\n\t"
        "mul %A1,%2\n\t"
        "movw %A0,r0\n\t"
        /* 25*x0 = 2*(13*x0)-x0. Initialize the upper word with
         * that contribution instead of clearing it and multiplying later. */
        "movw %C0,r0\n\t"
        "lsl %C0\n\t"
        "rol %D0\n\t"
        "sub %C0,%A1\n\t"
        "sbc %D0,r2\n\t"
        "mul %B1,%2\n\t"
        "add %B0,r0\n\t"
        "adc %C0,r1\n\t"
        "adc %D0,r2\n\t"
        /* Only the low byte of 25*x1 contributes at bit 24. */
        "lsl r0\n\t"
        "sub r0,%B1\n\t"
        "add %D0,r0\n\t"
        "mul %C1,%2\n\t"
        "add %C0,r0\n\t"
        "adc %D0,r1\n\t"
        "mul %D1,%2\n\t"
        "add %D0,r0\n\t"
        "mul %A1,%3\n\t"
        "add %B0,r0\n\t"
        "adc %C0,r1\n\t"
        "adc %D0,r2\n\t"
        "mul %B1,%3\n\t"
        "add %C0,r0\n\t"
        "adc %D0,r1\n\t"
        "mul %C1,%3\n\t"
        "add %D0,r0\n\t"
        "subi %A0,0xa1\n\t"
        "sbci %B0,0x0c\n\t"
        "sbci %C0,0x91\n\t"
        "sbci %D0,0xc3\n\t"
        "clr __zero_reg__\n\t"
        : "=&d"(result)
        : "r"(value), "d"((uint8_t)13), "d"((uint8_t)102)
        : "r0", "r1", "r2", "cc");
    return result;
#else
    return speex_low_rng_next_c(value);
#endif
}
#endif
