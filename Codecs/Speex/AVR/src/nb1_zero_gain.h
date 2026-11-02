/* Exact unity-minus-one Q15 scaling for NB1 zero-pulse-gain preparation.
 * Original project identities; Xiph algorithm provenance remains unchanged. */
#ifndef MICROMUSIC_SPEEX_NB1_ZERO_GAIN_H
#define MICROMUSIC_SPEEX_NB1_ZERO_GAIN_H
#include "speex_platform.h"

/* Full signed16 domain, including -32768 -> -32767. */
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_nb1_unity_q15_c(int16_t n)
{return n-(n>0)+(n==INT16_MIN);}

/* speex_low_noise_values5 has scale 0..121000000 and words in
 * -14771..14771. In particular -32768 is impossible, removing its correction.
 * floor(32767*n/32768) = n-(n>0), with exact negative floor semantics. */
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_nb1_noise_unity_c(int16_t n)
{return n-(n>0);}
#endif
