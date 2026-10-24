#ifndef SPEEX_WB_IIR_H
#define SPEEX_WB_IIR_H
#include "speex_platform.h"
void speex_wb_iir40_c(const int16_t *,const int16_t *,int16_t *,int32_t *);
#if SPEEX_NB3_USE_AVR_ASM
void speex_wb_iir40_avr(const int16_t *,const int16_t *,int16_t *,int32_t *);
#define speex_wb_iir40 speex_wb_iir40_avr
#else
#define speex_wb_iir40 speex_wb_iir40_c
#endif
#endif
