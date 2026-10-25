#include "fluid.h"
static mm_fluid_state state;
static uint8_t waves[3][4][256];
static uint8_t minimum_sum, maximum_sum;
void set_wave(unsigned bank, unsigned stage, unsigned index, unsigned value) {
    if (bank < 3 && stage < 4 && index < 256) waves[bank][stage][index] = (uint8_t)value;
}
void set_mix(unsigned minimum, unsigned maximum) { minimum_sum = (uint8_t)minimum; maximum_sum = (uint8_t)maximum; }
void reset(void) { mm_fluid_init(&state); }
unsigned frame(unsigned bc, unsigned de, unsigned bank, unsigned piano_stage, unsigned guitar_stage, unsigned final_frame) {
    return mm_fluid_frame(&state, (uint16_t)bc, (uint16_t)de, waves[bank][piano_stage], waves[2][guitar_stage],
        minimum_sum, maximum_sum, (uint8_t)final_frame);
}
unsigned phase_bc(void) { return state.phase_bc; }
unsigned phase_de(void) { return state.phase_de; }
unsigned mix(unsigned piano, unsigned guitar, unsigned low, unsigned high) {
    return mm_fluid_mix_c((uint8_t)piano, (uint8_t)guitar, (uint8_t)low, (uint8_t)high);
}
int asm_enabled(void) { return MM_FLUID_I8080_ASM_ENABLED; }
