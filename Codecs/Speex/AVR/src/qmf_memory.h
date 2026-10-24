/* Experimental exact fixed-point synthesis for Speex's 64-tap QMF.
 * Input is [low half, high half] in pcm; output replaces the same buffer.
 * Each history is 32 int16 values, initially zero. N must be a multiple of 64.
 * This saves the upstream two (N/2+32)-sample temporary arrays, plus half of
 * its sparsely used persistent histories. It does not make WB real-time. */
#ifndef SPEEX_AVR_QMF_MEMORY_H
#define SPEEX_AVR_QMF_MEMORY_H
#include <stdint.h>
void speex_avr_qmf_memory(int16_t *pcm, uint16_t n,
                          int16_t *low_history, int16_t *high_history);
#endif
