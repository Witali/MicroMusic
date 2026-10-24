/*
 * Speex NB mode 3 (8000 bit/s, 8 kHz) experimental decoder.
 * Based on the Xiph Speex 1.2.1 format and fixed-point algorithms.
 * The original codec and codebooks are BSD-3-Clause, see LICENSE-SPEEX.txt.
 * This implementation is an experimental restricted-profile port,
 * NOT yet certified bit-exact or realtime-safe on AVR.
 */
#ifndef SPEEX_NB8_H
#define SPEEX_NB8_H
#include <stdint.h>
#define NB8_BYTES 20
#define NB8_SAMPLES 160
#define NB8_RATE 8000

typedef struct {
    int16_t history[256];   /* circular excitation history */
    int32_t synth_mem[10];  /* all-pole LPC state */
    int16_t old_lsp[10];
    int16_t previous_lpc[10]; /* one-subframe delay, as in Xiph decoder */
    uint16_t sample_index;
    uint8_t started;
} SpeexNB8;

void speex_nb8_init(SpeexNB8 *state);
/* Validates prefix/mode and decodes precisely one 160-bit Speex mode-3 frame.
 * input: 20 bytes in standard Speex MSB-first mode-3 bit order, NOT Ogg/Speex.
 * output: 160 signed 16-bit PCM samples, 8 kHz. Postfilter/highpass off.
 * return 0 on success, -1 for unsupported mode.
 */
int speex_nb8_decode(SpeexNB8 *state, const uint8_t input[NB8_BYTES], int16_t pcm[NB8_SAMPLES]);
#endif
