#ifndef MICROMUSIC_I8080_FLUID_H
#define MICROMUSIC_I8080_FLUID_H
#include <stdint.h>

#if defined(__8080) && __8080 && defined(MICROMUSIC_ENABLE_I8080_ASM) && MICROMUSIC_ENABLE_I8080_ASM
#define MM_FLUID_I8080_ASM_ENABLED 1
#else
#define MM_FLUID_I8080_ASM_ENABLED 0
#endif
#define MM_FLUID_RESET_PHASE ((uint16_t)0xff00)
typedef struct { uint16_t phase_bc, phase_de; uint8_t level; } mm_fluid_state;
void mm_fluid_init_c(mm_fluid_state *state);
uint8_t mm_fluid_mix_c(uint8_t piano, uint8_t guitar, uint8_t minimum_sum, uint8_t maximum_sum);
/* Steps: 0000..FEFF or FF00 (reset phase to zero). Caller supplies ordinary
 * sample arrays and the bank for the NEXT output sample. Device memory access,
 * score traversal and output timing belong to the caller. No C timing promise.
 * Return the previous level, advance phases, then calculate the next level.
 * A final frame still advances phases but does not read the next sample bank. */
uint8_t mm_fluid_frame_c(mm_fluid_state *state, uint16_t step_bc, uint16_t step_de,
    const uint8_t piano[256], const uint8_t guitar[256], uint8_t minimum_sum,
    uint8_t maximum_sum, uint8_t final_frame);
/* Always selectable on 8080 too. Bare-ROM ASM has a separate register ABI and
 * requires an explicit build architecture plus enable flag; C remains default. */
#define mm_fluid_init mm_fluid_init_c
#define mm_fluid_frame mm_fluid_frame_c
#endif
