#ifndef MICROMUSIC_I8080_VOICE_H
#define MICROMUSIC_I8080_VOICE_H
#include <stdint.h>

/* Real z88dk CPU macro plus separate opt-in. Never redefine target macros. */
#if defined(__8080) && __8080 && defined(MICROMUSIC_ENABLE_I8080_ASM) && MICROMUSIC_ENABLE_I8080_ASM
#define MM_VOICE_I8080_ASM_ENABLED 1
#else
#define MM_VOICE_I8080_ASM_ENABLED 0
#endif

/* Caller supplies an ordinary byte: device memory access is outside arithmetic.
 * index=0 reads the low nibble, index=1 the high nibble. No timing guarantee. */
uint8_t mm_voice_nibble_c(uint8_t packed, uint8_t index);
uint8_t mm_voice_width_c(uint8_t level);
/* C remains the default and explicitly callable even on an enabled 8080.
 * The ROM is a separate, explicitly selected backend with its own register ABI. */
#define mm_voice_nibble mm_voice_nibble_c
#define mm_voice_width mm_voice_width_c
#endif
