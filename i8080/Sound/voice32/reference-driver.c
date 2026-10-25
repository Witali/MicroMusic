#include "voice.h"

int asm_enabled(void) { return MM_VOICE_I8080_ASM_ENABLED; }
unsigned nibble(unsigned packed, unsigned index) {
    return mm_voice_nibble((uint8_t)packed, (uint8_t)index);
}
unsigned width(unsigned level) { return mm_voice_width((uint8_t)level); }
