/* Exact arithmetic shifts for AVR fixed-point hot paths. Align the result
 * at the next whole-byte boundary by shifting left, preserving the sign and
 * carry bits separately. Callers retain upstream's rounding/wrap semantics. */
#ifndef SPEEX_AVR_SHIFT_H
#define SPEEX_AVR_SHIFT_H
#include <stdint.h>
#ifdef __AVR__
#define SPEEX_AVR_ASR(name,extra) \
static inline __attribute__((always_inline)) int32_t name(int32_t value) \
{ \
    __asm__ ( \
        "lsl %B0\n\t" \
        "rol %C0\n\t" \
        "rol %D0\n\t" \
        "sbc %A0,%A0\n\t" \
        ".rept " #extra "\n\t" \
        "lsl %B0\n\t" \
        "rol %C0\n\t" \
        "rol %D0\n\t" \
        "rol %A0\n\t" \
        ".endr\n\t" \
        "mov r0,%A0\n\t" \
        "mov %A0,%C0\n\t" \
        "mov %B0,%D0\n\t" \
        "mov %C0,r0\n\t" \
        "sbc %D0,%D0\n\t" \
        : "+r" (value) : : "r0", "cc" \
    ); \
    return value; \
}
SPEEX_AVR_ASR(speex_avr_asr13,2)
SPEEX_AVR_ASR(speex_avr_asr14,1)
#undef SPEEX_AVR_ASR
static inline __attribute__((always_inline)) int32_t speex_avr_asr15(int32_t value)
{
    __asm__ (
        "lsl %B0\n\trol %C0\n\trol %D0\n\t"
        "mov %A0,%C0\n\tmov %B0,%D0\n\t"
        "sbc %C0,%C0\n\tmov %D0,%C0\n\t"
        : "+r"(value) : : "cc");
    return value;
}
#define SPEEX_AVR_ASR_WORD(name,left) \
static inline __attribute__((always_inline)) int16_t name(int32_t value) \
{ \
    __asm__ ( \
        ".rept " #left "\n\t" \
        "lsl %B0\n\trol %C0\n\trol %D0\n\t" \
        ".endr\n\t" \
        "mov %A0,%C0\n\tmov %B0,%D0\n\t" \
        : "+r"(value) : : "cc"); \
    return (int16_t)value; \
}
SPEEX_AVR_ASR_WORD(speex_avr_asr14_word,2)
SPEEX_AVR_ASR_WORD(speex_avr_asr15_word,1)
#undef SPEEX_AVR_ASR_WORD
#else
static inline int32_t speex_avr_asr13(int32_t value){return value>>13;}
static inline int32_t speex_avr_asr14(int32_t value){return value>>14;}
static inline int32_t speex_avr_asr15(int32_t value){return value>>15;}
static inline int16_t speex_avr_asr14_word(int32_t value){return (int16_t)(value>>14);}
static inline int16_t speex_avr_asr15_word(int32_t value){return (int16_t)(value>>15);}
#endif
#endif
