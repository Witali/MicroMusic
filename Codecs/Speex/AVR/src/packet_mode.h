/* Enabled packet modes, shared by public validation and WB field offsets.
 * Original mode bit counts: Xiph 1.2.1 modes.c, BSD in vendor COPYING. */
#ifndef MICROMUSIC_SPEEX_PACKET_MODE_H
#define MICROMUSIC_SPEEX_PACKET_MODE_H
#include "speex_platform.h"
static inline unsigned speex_nb_packet_bits(uint8_t mode)
{
    switch(mode) {
    case 3:return 160;
#if SPEEX_ENABLE_NB4
    case 4:return 220;
#endif
#if SPEEX_ENABLE_NB2
    case 2:return 119;
#endif
#if SPEEX_ENABLE_NB8
    case 8:return 79;
#endif
#if SPEEX_ENABLE_NB1
    case 1:return 43;
#endif
    default:return 0;
    }
}
/* Private reader: prevalidated packet, 1..7 bits, within meaningful bits.
 * Read a second byte only when needed; never read padding beyond the packet. */
static inline uint8_t speex_packet_field(const uint8_t *p,unsigned bit,uint8_t n)
{
    unsigned at=bit>>3;uint8_t shift=bit&7;
    uint16_t value=(uint16_t)p[at]<<8;
    if(shift+n>8)value|=p[at+1];
    return (uint8_t)((value>>(16-shift-n))&((1u<<n)-1));
}
#endif
