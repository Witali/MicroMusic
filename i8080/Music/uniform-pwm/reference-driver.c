/* Test/analysis adapter. Hardware access is deliberately outside the library. */
#include "music.h"
static mm_music_state state;
void reset(void) { mm_music_init(&state); }
unsigned frame(unsigned bc, unsigned de) {
    return mm_music_frame(&state, (uint16_t)bc, (uint16_t)de);
}
unsigned phase_bc(void) { return state.phase_bc; }
unsigned phase_de(void) { return state.phase_de; }
unsigned asm_enabled(void) { return MM_MUSIC_I8080_ASM_ENABLED; }
