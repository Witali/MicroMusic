#ifndef SPEEX_WB_FOLD_H
#define SPEEX_WB_FOLD_H
#include "speex_platform.h"
void speex_wb_fold40_c(int16_t *,int32_t);
void speex_wb_excitation8_40_c(int16_t *,const uint8_t *,int32_t,int32_t);
/* Private NB3 layout: four read-only indices 0..31 -> forty output samples.
 * Scale 0..121000000; g signed32. Output must not overlap the indices. */
void speex_wb_excitation40_c(int16_t *,const uint8_t *,int32_t,int32_t);
#if SPEEX_ENABLE_NB1
/* Readonly 208-byte NB1 workspace, sub 0..3; output40/scratch5/cache disjoint.
 * Q15 noise words are prepared once per frame, class2 is exactly zero. Apply
 * the second quantizer to the other words, then lookup/negate odd positions. */
void speex_wb_fold5_c(int16_t *,int32_t);
void speex_wb_noise_scale5_c(int16_t *,int32_t);
void speex_wb_noise_fold40_c(int16_t *,const int16_t *,uint8_t,int32_t,int16_t *);
#if SPEEX_NB3_USE_AVR_ASM
void speex_wb_fold5_avr(int16_t *,int32_t);
void speex_wb_noise_scale5_avr(int16_t *,int32_t);
void speex_wb_noise_fold40_avr(int16_t *,const int16_t *,uint8_t,int32_t,int16_t *);
#define speex_wb_noise_fold40 speex_wb_noise_fold40_avr
#else
#define speex_wb_noise_fold40 speex_wb_noise_fold40_c
#endif
#endif
#if SPEEX_ENABLE_NB2 || SPEEX_ENABLE_NB8
void speex_wb_excitation_low40(int16_t *,const uint8_t *,int32_t,int32_t,uint8_t);
#endif
#if SPEEX_NB3_USE_AVR_ASM
void speex_wb_fold40_avr(int16_t *,int32_t);
#define speex_wb_fold40 speex_wb_fold40_avr
void speex_wb_excitation8_40_avr(int16_t *,const uint8_t *,int32_t,int32_t);
#define speex_wb_excitation8_40 speex_wb_excitation8_40_avr
void speex_wb_excitation40_avr(int16_t *,const uint8_t *,int32_t,int32_t);
#define speex_wb_excitation40 speex_wb_excitation40_avr
#else
#define speex_wb_fold40 speex_wb_fold40_c
#define speex_wb_excitation8_40 speex_wb_excitation8_40_c
#define speex_wb_excitation40 speex_wb_excitation40_c
#endif
#endif
