#ifndef SPEEX_WB_FOLD_H
#define SPEEX_WB_FOLD_H
#include "speex_platform.h"
void speex_wb_fold40_c(int16_t *,int32_t);
/* Private NB3 layout: four read-only indices 0..31 -> forty output samples.
 * Scale 0..121000000; g signed32. Output must not overlap the indices. */
void speex_wb_excitation40_c(int16_t *,const uint8_t *,int32_t,int32_t);
#if SPEEX_NB3_USE_AVR_ASM
void speex_wb_fold40_avr(int16_t *,int32_t);
#define speex_wb_fold40 speex_wb_fold40_avr
void speex_wb_excitation40_avr(int16_t *,const uint8_t *,int32_t,int32_t);
#define speex_wb_excitation40 speex_wb_excitation40_avr
#else
#define speex_wb_fold40 speex_wb_fold40_c
#define speex_wb_excitation40 speex_wb_excitation40_c
#endif
#endif
