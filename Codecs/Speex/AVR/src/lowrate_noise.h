/* Exact Xiph noise innovation, shared by NB vocoder and HB1 reconstruction. */
#ifndef MICROMUSIC_SPEEX_LOWRATE_NOISE_H
#define MICROMUSIC_SPEEX_LOWRATE_NOISE_H
#include "speex_platform.h"
#include "nb1_cache_layout.h"
#if SPEEX_ENABLE_NB1
/* NB1's positive gain table: 0 <= scale <=121000000; output has five words. */
void speex_low_noise_values5(int16_t *,int32_t);
void speex_low_noise_indices40(uint8_t *,uint32_t *);
#endif
#endif
