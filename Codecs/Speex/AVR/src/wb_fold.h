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
/* Enabled mode2: four 10-word rows/index 0..15; mode8: two 20-word rows/index 0..31.
 * Output40 and readonly indices do not overlap. Scale 0..121000000, g signed32.
 * Explicit C retains separate reconstruction/folding and remains callable. */
void speex_wb_excitation_low40_c(int16_t *,const uint8_t *,int32_t,int32_t,uint8_t);
#if SPEEX_NB3_USE_AVR_ASM
#if SPEEX_ENABLE_NB2
void speex_wb_excitation_nb2_40_avr(int16_t *,const uint8_t *,int32_t,int32_t);
#endif
#if SPEEX_ENABLE_NB8
void speex_wb_excitation_nb8_40_avr(int16_t *,const uint8_t *,int32_t,int32_t);
#endif
/* The sole production caller already knows the mode; expose this small
 * dispatch so it can share the caller's branch and omit a five-argument call. */
static SPEEX_NB3_ALWAYS_INLINE void speex_wb_excitation_low40_avr(int16_t *exc,
    const uint8_t *indices,int32_t scale,int32_t g,uint8_t mode)
{
#if SPEEX_ENABLE_NB2 && SPEEX_ENABLE_NB8
    if(mode==2)speex_wb_excitation_nb2_40_avr(exc,indices,scale,g);
    else speex_wb_excitation_nb8_40_avr(exc,indices,scale,g);
#elif SPEEX_ENABLE_NB2
    (void)mode;speex_wb_excitation_nb2_40_avr(exc,indices,scale,g);
#else
    (void)mode;speex_wb_excitation_nb8_40_avr(exc,indices,scale,g);
#endif
}
#define speex_wb_excitation_low40 speex_wb_excitation_low40_avr
#else
#define speex_wb_excitation_low40 speex_wb_excitation_low40_c
#endif
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
