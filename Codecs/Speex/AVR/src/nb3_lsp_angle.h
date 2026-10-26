/* Exact Xiph 1.2.1 ANGLE2X, full signed16 input domain.
 * Polynomial/rounding adapted from math_approx.h, Jean-Marc Valin;
 * BSD terms in vendor/speex-1.2.1/COPYING. No table or hardware access.
 * P13(a,b)=floor((a*b+4096)/8192), with signed16 operands. After the
 * square/cast, y spans signed16; a is 300..380, b lies in -5616..-2576.
 * All products and rebias constants fit signed32. ASM retains each P13
 * before the next word cast; final modulo16 shift keeps the same bits. */
#ifndef MICROMUSIC_NB3_LSP_ANGLE_H
#define MICROMUSIC_NB3_LSP_ANGLE_H
#include "speex_platform.h"
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_nb3_lsp_angle_c(int16_t x)
{
    uint8_t negative=x>=12868;
    if(negative)x=(int16_t)(25736-(int32_t)x);
    int16_t y=(int16_t)(((int32_t)x*x+4096)>>13);
    int16_t a=(int16_t)(340+((4096-10*(int32_t)y)>>13));
    int16_t b=(int16_t)(-4096+(((int32_t)y*a+4096)>>13));
    int32_t p=((int32_t)y*b+4096)>>13;
    int16_t c=(int16_t)(negative?-8192-p:8192+p);
    return (int16_t)((uint16_t)c<<2);
}
#if SPEEX_NB3_USE_AVR_ASM
extern SPEEX_NB3_CONST int16_t speex_avr_lsp_angle(int16_t);
#endif
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_nb3_lsp_angle(int16_t x)
{
#if SPEEX_NB3_USE_AVR_ASM
    return speex_avr_lsp_angle(x);
#else
    return speex_nb3_lsp_angle_c(x);
#endif
}
#endif
