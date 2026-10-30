/* Exact Xiph noise innovation, shared by NB vocoder and HB1 regeneration. */
#ifndef MICROMUSIC_SPEEX_LOWRATE_NOISE_H
#define MICROMUSIC_SPEEX_LOWRATE_NOISE_H
#include "speex_platform.h"
#if SPEEX_ENABLE_NB1
void speex_low_noise40(int16_t *,uint32_t *,int32_t);
void speex_low_noise_values5(int16_t *,int32_t);
void speex_low_noise_indices40(uint8_t *,uint32_t *);
#endif
#endif
