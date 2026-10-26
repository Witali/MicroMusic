#include "voice.h"

uint8_t mm_voice_nibble_c(uint8_t packed, uint8_t index) {
    return (uint8_t)((index ? packed >> 4 : packed) & 15);
}

uint8_t mm_voice_width_c(uint8_t level) {
    return (uint8_t)(4 + 4 * (level & 15));
}

uint8_t mm_voice_storage_code_c(uint8_t level) {
    level &= 15;
    return level == 4 ? 15 : level == 15 ? 4 : level;
}

uint8_t mm_voice_fast_level_c(uint8_t packed, uint8_t index) {
    return mm_voice_storage_code_c(mm_voice_nibble_c(packed, (uint8_t)!(index & 1)));
}

uint8_t mm_voice_record_count_c(uint8_t header) {
    return (uint8_t)(header - 1);
}

uint8_t mm_voice_rle_step_c(uint8_t *remaining, uint8_t repeated) {
    *remaining = (uint8_t)(*remaining - 1);
    return !*remaining ? MM_VOICE_READ_LINK : repeated ? MM_VOICE_KEEP_WORD : MM_VOICE_READ_WORD;
}
