/* Quarter-scale dequantization derived from Xiph Speex 1.2.1 quant_lsp.c.
 * Copyright (C) 2002 Jean-Marc Valin; BSD terms in vendor/speex-1.2.1/COPYING.
 * Private map of a validated 20-byte NB3 packet: three six-bit LSP codes
 * begin at bit 5; the five-bit frame gain begins at bit 23.
 * Original raw angles are 16*((i+1)*128 + 2*base + correction), hence
 * dividing by four is exact, including negative values. The byte bounds
 * imply units in [-256,1661], quarters in [-1024,6644] and raw angles in
 * [-4096,26576]; all intermediates fit signed16 on AVR as well as hosts.
 * Output ten quarters into storage disjoint from the immutable packet.
 * The caller initializes raw state and zero deltas on reset, or subtracts
 * old raw quarters on a changed frame. Equal cached frames need no call.
 * Pure C for every arithmetic backend; Flash reads remain platform-specific. */
#ifndef SPEEX_NB3_LSP_H
#define SPEEX_NB3_LSP_H
#include "avr_tables.h"
extern const signed char cdbk_nb[],cdbk_nb_low1[],cdbk_nb_high1[];

static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_lsp_quarters(
    const uint8_t *packet,int16_t *out)
{
    const uint8_t a=((packet[0]&7)<<3)|(packet[1]>>5);
    const uint8_t b=((packet[1]&31)<<1)|(packet[2]>>7);
    const uint8_t c=(packet[2]>>1)&63;
    const int8_t *base=cdbk_nb+10*(unsigned)a;
    const int8_t *low=cdbk_nb_low1+5*(unsigned)b,*high=cdbk_nb_high1+5*(unsigned)c;
    uint8_t i;
    for(i=0;i<5;i++)out[i]=4*((i+1)*128+2*(int16_t)AVR_READ_I8(base+i)+(int16_t)AVR_READ_I8(low+i));
    for(i=0;i<5;i++)out[i+5]=4*((i+6)*128+2*(int16_t)AVR_READ_I8(base+5+i)+(int16_t)AVR_READ_I8(high+i));
}

static SPEEX_NB3_ALWAYS_INLINE uint8_t speex_nb3_frame_gain(const uint8_t *packet)
{
    return ((packet[2]&1)<<4)|(packet[3]>>4);
}
#endif
