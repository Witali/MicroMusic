/* Exact arithmetic shifts for AVR fixed-point hot paths. Discard one whole
 * byte, then shift only the remaining signed 24-bit value. No rounding is
 * introduced: callers retain upstream's bias and modulo-32 additions. */
#ifndef SPEEX_AVR_SHIFT_H
#define SPEEX_AVR_SHIFT_H
#include <stdint.h>
#ifdef __AVR__
#define SPEEX_AVR_ASR(name,bits) \
static inline __attribute__((always_inline)) int32_t name(int32_t value) \
{ \
    __asm__ ( \
        "mov %A0,%B0\n\t" \
        "mov %B0,%C0\n\t" \
        "mov %C0,%D0\n\t" \
        "lsl %D0\n\t" \
        "sbc %D0,%D0\n\t" \
        ".rept " #bits "\n\t" \
        "asr %C0\n\t" \
        "ror %B0\n\t" \
        "ror %A0\n\t" \
        ".endr\n\t" \
        : "+r" (value) : : "cc" \
    ); \
    return value; \
}
SPEEX_AVR_ASR(speex_avr_asr13,5)
SPEEX_AVR_ASR(speex_avr_asr14,6)
SPEEX_AVR_ASR(speex_avr_asr15,7)
#undef SPEEX_AVR_ASR
#else
static inline int32_t speex_avr_asr13(int32_t value){return value>>13;}
static inline int32_t speex_avr_asr14(int32_t value){return value>>14;}
static inline int32_t speex_avr_asr15(int32_t value){return value>>15;}
#endif
#endif
