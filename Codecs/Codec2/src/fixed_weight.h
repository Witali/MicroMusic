/* Portable C weighted LPC spectrum. Explicit block scale, no mutable globals. */
#ifndef MICROMUSIC_CODEC2_FIXED_WEIGHT_H
#define MICROMUSIC_CODEC2_FIXED_WEIGHT_H
#include "compact_fft.h"
#include <stdint.h>
typedef struct { int32_t coefficient[11]; int exponent; } codec2_weight;
void codec2_weight_init(codec2_weight *state,const float coefficient[11]);
compact_complex codec2_weight_dc(const codec2_weight *state);
void codec2_weight_pair(const codec2_weight *state,unsigned k,compact_complex *positive,compact_complex *negative);
#endif
