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
/* Lossless fast-ROM storage: swap codes 4/15, high nibble first. Device
 * reads and literal/RLE record traversal stay outside these pure functions. */
uint8_t mm_voice_storage_code_c(uint8_t level);
uint8_t mm_voice_fast_level_c(uint8_t packed, uint8_t index);
enum { MM_VOICE_KEEP_WORD = 0, MM_VOICE_READ_WORD = 1, MM_VOICE_READ_LINK = 2 };
uint8_t mm_voice_record_count_c(uint8_t header);
/* Call once per expanded four-sample word. Remaining must start in 1..255. */
uint8_t mm_voice_rle_step_c(uint8_t *remaining, uint8_t repeated);
/* C remains the default and explicitly callable even on an enabled 8080.
 * The ROM is a separate, explicitly selected backend with its own register ABI. */
#define mm_voice_nibble mm_voice_nibble_c
#define mm_voice_width mm_voice_width_c
#define mm_voice_fast_level mm_voice_fast_level_c
#endif
