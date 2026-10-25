#include "music.h"

void mm_music_init_c(mm_music_state *state) {
    state->phase_bc = 0;
    state->phase_de = 0;
    state->level = 0;
}

static uint16_t advance_phase(uint16_t phase, uint16_t step) {
    if (step == MM_MUSIC_RESET_PHASE) return (uint16_t)0x8000;
    return (uint16_t)(phase + step);
}

uint8_t mm_music_frame_c(mm_music_state *state, uint16_t step_bc, uint16_t step_de) {
    uint8_t output = state->level;
    uint16_t sum;
    state->phase_bc = advance_phase(state->phase_bc, step_bc);
    state->phase_de = advance_phase(state->phase_de, step_de);
    sum = (uint16_t)((state->phase_bc >> 8) + (state->phase_de >> 8));
    state->level = (uint8_t)(sum >> 5);
    return output;
}
