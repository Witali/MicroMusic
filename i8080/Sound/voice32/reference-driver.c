#include "voice.h"

int asm_enabled(void) { return MM_VOICE_I8080_ASM_ENABLED; }
unsigned nibble(unsigned packed, unsigned index) {
    return mm_voice_nibble((uint8_t)packed, (uint8_t)index);
}
unsigned width(unsigned level) { return mm_voice_width((uint8_t)level); }
unsigned storage(unsigned level) { return mm_voice_storage_code_c((uint8_t)level); }
unsigned fast_level(unsigned packed, unsigned index) { return mm_voice_fast_level((uint8_t)packed, (uint8_t)index); }
unsigned record_count(unsigned header) { return mm_voice_record_count_c((uint8_t)header); }
unsigned record_step(unsigned remaining, unsigned repeated) {
    uint8_t left = (uint8_t)remaining;
    uint8_t action = mm_voice_rle_step_c(&left, (uint8_t)repeated);
    return ((unsigned)left << 8) | action;
}
