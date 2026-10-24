/* AVR201 signed 16x16->32 multiply, transplanted unchanged from verified
 * R4 but only compiled for the upstream branch when enabled.
 * Call using the original Speex MULT16_16 macro.
 */
#ifndef SPEEX_AVR_FASTMUL_H
#define SPEEX_AVR_FASTMUL_H
#include <stdint.h>
static inline spx_word32_t speex_avr_mul_s16_s16(spx_word16_t lhs, spx_word16_t rhs) {
#ifdef __AVR__
    uint16_t lo, hi;
    /* Four hardware 8-bit multiplications, signed high-byte corrections. */
    __asm__ volatile (
        "clr r2\n\t"
        "muls %B2, %B3\n\t"
        "movw %A1, r0\n\t"
        "mul %A2, %A3\n\t"
        "movw %A0, r0\n\t"
        "mulsu %B2, %A3\n\t"
        "sbc %B1, r2\n\t"
        "add %B0, r0\n\t"
        "adc %A1, r1\n\t"
        "adc %B1, r2\n\t"
        "mulsu %B3, %A2\n\t"
        "sbc %B1, r2\n\t"
        "add %B0, r0\n\t"
        "adc %A1, r1\n\t"
        "adc %B1, r2\n\t"
        "clr __zero_reg__\n\t"
        : "=&r" (lo), "=&r" (hi)
        : "a" (lhs), "a" (rhs)
        : "r0", "r1", "r2", "cc"
    );
    return (spx_word32_t)(((uint32_t)hi << 16) | lo);
#else
    return (spx_word32_t)lhs * (spx_word32_t)rhs;
#endif
}

#undef MULT16_16
#define MULT16_16(a,b) speex_avr_mul_s16_s16((spx_word16_t)(a),(spx_word16_t)(b))
#endif
