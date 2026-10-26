/* Xiph mode 4: same 28-bit frame prefix, four 48-bit subframes.
 * Each subframe has pitch7/gain5/energy1 followed by five 7-bit indices.
 * Seven-byte windows are bounded by the meaningful 220 bits of 28 bytes.
 * Private contract: validated NB4 packet, sub0..3 and five writable index
 * bytes disjoint from the read-only packet. Padding bits are ignored. */
#ifndef MICROMUSIC_NB4_SUBFRAME_H
#define MICROMUSIC_NB4_SUBFRAME_H
#include "speex_platform.h"
static SPEEX_NB3_STAGE_O2 uint16_t speex_nb4_unpack_subframe(const uint8_t *packet,uint8_t sub,uint8_t indices[5])
{
    const uint8_t *p=packet+3+6*sub;
    uint8_t a=p[0],b=p[1],c=p[2],d=p[3],e=p[4],f=p[5],g=p[6];
    indices[0]=c&127;indices[1]=d>>1;indices[2]=((d&1)<<6)|(e>>2);
    indices[3]=((e&3)<<5)|(f>>3);indices[4]=((f&7)<<4)|(g>>4);
    return ((uint16_t)(a&15)<<9)|((uint16_t)b<<1)|(c>>7);
}
#endif
