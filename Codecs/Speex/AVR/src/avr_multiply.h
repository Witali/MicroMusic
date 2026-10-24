/* Exact signed 16x16 -> 32 AVR multiply. AVR201 arithmetic, as retained in
 * reference/R4; see the cookbook's official source link. A single early-
 * clobber output keeps all four result bytes together for AVR GCC and avoids
 * reconstructing the result from two independent uint16_t output operands. */
#ifndef SPEEX_AVR_MULTIPLY_H
#define SPEEX_AVR_MULTIPLY_H
#include <stdint.h>
#include "speex_platform.h"
static SPEEX_NB3_ALWAYS_INLINE
int32_t speex_avr_mul_s16_s16(int16_t lhs, int16_t rhs)
{
#if SPEEX_NB3_USE_AVR_ASM
    int32_t result;
    __asm__ (
        "clr r2\n\t"
        "muls %B1, %B2\n\t"
        "movw %C0, r0\n\t"
        "mul %A1, %A2\n\t"
        "movw %A0, r0\n\t"
        "mulsu %B1, %A2\n\t"
        "sbc %D0, r2\n\t"
        "add %B0, r0\n\t"
        "adc %C0, r1\n\t"
        "adc %D0, r2\n\t"
        "mulsu %B2, %A1\n\t"
        "sbc %D0, r2\n\t"
        "add %B0, r0\n\t"
        "adc %C0, r1\n\t"
        "adc %D0, r2\n\t"
        "clr __zero_reg__\n\t"
        : "=&r" (result)
        : "a" (lhs), "a" (rhs)
        : "r0", "r1", "r2", "cc"
    );
    return result;
#else
    return (int32_t)lhs * rhs;
#endif
}
#undef MULT16_16
#define MULT16_16(a,b) speex_avr_mul_s16_s16((int16_t)(a),(int16_t)(b))
#endif
