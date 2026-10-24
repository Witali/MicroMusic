#ifndef SPEEX_WB_FOLD_H
#define SPEEX_WB_FOLD_H
#include "speex_platform.h"
void speex_wb_fold40_c(int16_t *,int32_t);
#if SPEEX_NB3_USE_AVR_ASM
void speex_wb_fold40_avr(int16_t *,int32_t);
#define speex_wb_fold40 speex_wb_fold40_avr
#else
#define speex_wb_fold40 speex_wb_fold40_c
#endif
#endif
