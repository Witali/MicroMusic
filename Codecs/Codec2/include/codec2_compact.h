/* Complete Codec2 3200 C decoder with reduced working memory, LGPL-2.1.
 * Original Codec2 sources/notices: vendor/codec2-1.2.0. No arithmetic ASM backend.
 */
#ifndef MICROMUSIC_CODEC2_COMPACT_H
#define MICROMUSIC_CODEC2_COMPACT_H
#include <stddef.h>
#include <stdint.h>

typedef struct {
    float tail[79];
    float previous_lsp[10];
    float previous_wo;
    float previous_energy;
    float excitation_phase;
    float background;
    uint32_t random_state;
    uint8_t previous_voiced;
    uint8_t initialized;
} codec2_compact;

int codec2_compact_init(codec2_compact *state);
/* Full eight-byte Codec2 3200 -> 160 PCM16 samples, mono 8 kHz.
 * Invalid pointers/length/uninitialized state return -1 without changing output
 * or state. Input, state and output must not overlap. No heap or global state.
 * A memory fit alone does not establish real-time or interrupt-active playback.
 */
int codec2_compact_decode(codec2_compact *state, const uint8_t *packet,
                         size_t length, int16_t pcm[160]);
#endif
