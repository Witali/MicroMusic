#ifndef SPEEX_WB_INTERNAL_H
#define SPEEX_WB_INTERNAL_H
#include <stdint.h>
int16_t *speex_wb_low_buffer(void);
void speex_wb_low_ready(const int16_t *,const int16_t *,const uint8_t *,int32_t);
int speex_wb_decode_low(const uint8_t *);
void speex_wb_lsp8(const int16_t *,int16_t *);
#endif
