/* Exact bounded forced-pitch arithmetic, Xiph Speex submodes 1 and 8.
 * Original project specializations; retain the codec's Xiph BSD provenance. */
#ifndef MICROMUSIC_SPEEX_FORCED_MATH_H
#define MICROMUSIC_SPEEX_FORCED_MATH_H
#include "speex_platform.h"

/* code 0..15: 2185*code+256 <=33031, so unsigned16 suffices.
 * This returns 0..64; submode8 retains its separate clamp to63. */
static SPEEX_NB3_ALWAYS_INLINE uint8_t speex_forced_coefficient_c(uint8_t code)
{return (uint16_t)(2185u*code+256u)>>9;}

/* x is signed16, c is 0..63. Original Q13(x*(c<<7)+4096) is
 * exactly (x*c+32)>>6, including negative ties toward positive infinity.
 * The signed22 product plus bias fits; the rounded result fits signed16. */
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_forced_q6_c(int16_t x,uint8_t c)
{return (int16_t)(((int32_t)x*c+32)>>6);}

static SPEEX_NB3_ALWAYS_INLINE int16_t speex_forced_q6(int16_t x,uint8_t c)
{
#if SPEEX_NB3_USE_AVR_ASM
    int16_t result;uint8_t low;
    __asm__ (
        "mulsu %B2,%3\n\tmovw %A0,r0\n\t"
        "mul %A2,%3\n\tmov %1,r0\n\tadd %A0,r1\n\t"
        "clr __zero_reg__\n\tadc %B0,__zero_reg__\n\t"
        /* Signed24 +32, followed by extraction of bits6..21. */
        "subi %1,224\n\tsbci %A0,255\n\tsbci %B0,255\n\t"
        "lsl %1\n\trol %A0\n\trol %B0\n\t"
        "lsl %1\n\trol %A0\n\trol %B0\n\t"
        : "=&w"(result),"=&d"(low) : "a"(x),"a"(c) : "r0","r1","cc");
    return result;
#else
    return speex_forced_q6_c(x,c);
#endif
}
#endif
