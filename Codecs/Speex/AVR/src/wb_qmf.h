#ifndef SPEEX_WB_QMF_H
#define SPEEX_WB_QMF_H
#include <stdint.h>
#include "speex_platform.h"
/* 8 pairs of signed16 half-sum/difference histories, mirrored (64 bytes).
 * A 40-pair block restores the cursor to zero; zero state on reset.
 * out may equal high-40 (the WB output buffer layout). No other overlap. */
void speex_wb_qmf40_c(const int16_t *,const int16_t *,int16_t *,uint8_t *);
#if SPEEX_NB3_USE_AVR_ASM
void speex_wb_qmf40_avr(const int16_t *,const int16_t *,int16_t *,uint8_t *);
#define speex_wb_qmf40 speex_wb_qmf40_avr
#else
#define speex_wb_qmf40 speex_wb_qmf40_c
#endif
#endif
