#include "voice.h"

uint8_t mm_voice_nibble_c(uint8_t packed, uint8_t index) {
    return (uint8_t)((index ? packed >> 4 : packed) & 15);
}

uint8_t mm_voice_width_c(uint8_t level) {
    return (uint8_t)(4 + 4 * (level & 15));
}
