/* Portable C weighted LPC spectrum. Explicit block scale, no mutable globals. */
#ifndef MICROMUSIC_CODEC2_FIXED_WEIGHT_H
#define MICROMUSIC_CODEC2_FIXED_WEIGHT_H
#include "compact_fft.h"
#include <stdint.h>
#ifndef CODEC2_WEIGHT_BITS
#define CODEC2_WEIGHT_BITS 24
#endif
#ifndef CODEC2_WEIGHT_TWIDDLE_Q
#define CODEC2_WEIGHT_TWIDDLE_Q 22
#endif
#ifndef CODEC2_WEIGHT_AVR_INT24
#define CODEC2_WEIGHT_AVR_INT24 0
#endif
#if CODEC2_WEIGHT_AVR_INT24
#if !defined(__AVR__) || !defined(__INT24_MAX__) || CODEC2_WEIGHT_BITS != 24 || CODEC2_WEIGHT_TWIDDLE_Q > 22
#error Explicit int24 storage requires a matching AVR compiler and 24-bit profile
#endif
typedef __int24 codec2_weight_component;
#else
typedef int32_t codec2_weight_component;
#endif
typedef struct { codec2_weight_component coefficient[11]; int exponent; } codec2_weight;
void codec2_weight_init(codec2_weight *state,const float coefficient[11]);
compact_complex codec2_weight_dc(const codec2_weight *state);
void codec2_weight_pair(const codec2_weight *state,unsigned k,compact_complex *positive,compact_complex *negative);
#endif
