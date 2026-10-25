#include "fluid.h"
void mm_fluid_init_c(mm_fluid_state *state) {
    state->phase_bc = 0; state->phase_de = 0; state->level = 8;
}
uint8_t mm_fluid_mix_c(uint8_t piano, uint8_t guitar, uint8_t minimum_sum, uint8_t maximum_sum) {
    int sum = (int)piano + guitar;
    unsigned span = (unsigned)maximum_sum - minimum_sum;
    if (maximum_sum <= minimum_sum) return 8;
    if (sum <= minimum_sum) return 0;
    if (sum >= maximum_sum) return 15;
    return (uint8_t)(((unsigned)(sum-minimum_sum)*15 + span/2)/span);
}
static uint16_t advance(uint16_t phase, uint16_t step) {
    return step == MM_FLUID_RESET_PHASE ? 0 : (uint16_t)(phase+step);
}
uint8_t mm_fluid_frame_c(mm_fluid_state *state, uint16_t step_bc, uint16_t step_de,
    const uint8_t piano[256], const uint8_t guitar[256], uint8_t minimum_sum,
    uint8_t maximum_sum, uint8_t final_frame) {
    uint8_t output = state->level;
    state->phase_bc = advance(state->phase_bc, step_bc);
    state->phase_de = advance(state->phase_de, step_de);
    if (!final_frame) state->level = mm_fluid_mix_c(piano[state->phase_bc >> 8],
        guitar[state->phase_de >> 8], minimum_sum, maximum_sum);
    return output;
}
