/* Complete mode-3200 algorithm with an explicitly selected fixed inverse FFT. */
#ifndef MICROMUSIC_CODEC2_HYBRID_H
#define MICROMUSIC_CODEC2_HYBRID_H
#include "codec2_compact.h"
typedef codec2_compact codec2_hybrid;
int codec2_hybrid_init(codec2_hybrid *state);
int codec2_hybrid_decode(codec2_hybrid *state, const uint8_t *packet, size_t length, int16_t pcm[160]);
#endif
