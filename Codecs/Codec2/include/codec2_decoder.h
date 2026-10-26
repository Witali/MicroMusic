/* Full mode-3200 float C baseline, LGPL-2.1.
 * Derived from Codec2 1.2.0. See vendor/codec2-1.2.0/COPYING and file notices.
 */
#ifndef MICROMUSIC_CODEC2_DECODER_H
#define MICROMUSIC_CODEC2_DECODER_H
#include <stddef.h>
#include <stdint.h>

#define CODEC2_DECODER_SAMPLES 160
#define CODEC2_DECODER_FFT_STORAGE 5504

/* Caller-owned state. An initialized instance must not be moved or copied:
 * the original KISS FFT config contains pointers into its own storage.
 * No heap allocation is requested. No hardware addresses or ASM backend.
 * Large-AVR correctness baseline, not a Tiny13 or real-time profile.
 */
typedef struct {
    union {
        void *pointer_alignment;
        float float_alignment;
        uint8_t bytes[CODEC2_DECODER_FFT_STORAGE];
    } fft_storage;
    void *fft_config;
    float synthesis_window[160];
    float overlap[160];
    float previous_lsp[10];
    float previous_wo;
    float previous_energy;
    float excitation_phase;
    float background;
    uint32_t random_state;
    uint16_t fft_bytes;
    uint8_t previous_voiced;
    uint8_t initialized;
} codec2_decoder;

/* Initialization includes FFT twiddles and the original Parzen window. */
int codec2_decoder_init(codec2_decoder *state);

/* Eight bytes of standard Codec2 3200 -> 160 s16 mono samples at 8 kHz.
 * All ten LSPs, full harmonic amplitudes, phase, both postfilters, and OLA.
 * Returns -1 on invalid pointers, length or uninitialized state, without
 * changing state/output. Input, state and output must not overlap.
 */
int codec2_decoder_decode(codec2_decoder *state, const uint8_t *packet,
                         size_t length, int16_t pcm[CODEC2_DECODER_SAMPLES]);
#endif
