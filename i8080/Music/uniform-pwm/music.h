#ifndef MICROMUSIC_I8080_MUSIC_H
#define MICROMUSIC_I8080_MUSIC_H

#include <stdint.h>

/* z88dk's real C CPU macro; never redefine a compiler's target macros here.
 * The timing-specific ROM is an explicit separate build, not a C-callable ABI.
 * This gate exposes its availability; the portable arithmetic stays callable
 * even on an 8080 with the assembly option enabled. */
#if defined(__8080) && __8080 && defined(MICROMUSIC_ENABLE_I8080_ASM) && MICROMUSIC_ENABLE_I8080_ASM
#define MM_MUSIC_I8080_ASM_ENABLED 1
#else
#define MM_MUSIC_I8080_ASM_ENABLED 0
#endif

#define MM_MUSIC_RESET_PHASE ((uint16_t)0xff00)

typedef struct {
    uint16_t phase_bc;
    uint16_t phase_de;
    uint8_t level;
} mm_music_state;

void mm_music_init_c(mm_music_state *state);
/* Return the level for this frame, then calculate the next frame.
 * Step range for the ROM backend: 0000..FEFF; FF00 resets a silent oscillator
 * to 8000. One frame has four equal PWM slots. Device I/O and scheduling belong
 * to the caller; this portable C fallback makes no timing guarantee. */
uint8_t mm_music_frame_c(mm_music_state *state, uint16_t step_bc, uint16_t step_de);

/* The normal library interface defaults to C on every architecture, including
 * 8080. Raw ROM assembly is selected only by build.py's explicit backend gate. */
#define mm_music_init mm_music_init_c
#define mm_music_frame mm_music_frame_c

#endif
