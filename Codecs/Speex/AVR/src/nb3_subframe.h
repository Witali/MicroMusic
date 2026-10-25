/* Private packet map from pinned Xiph Speex 1.2.1 nb_celp.c; bit slices are
 * derived here. NB3 has 5 mode bits, 18 LSP bits, 5 frame-gain bits,
 * then four 33-bit groups: pitch(7), adaptive gain(5), energy(1), indices(20).
 * Call only after validating a complete 20-byte NB mode-3 packet, with
 * sub in 0..3 and four writable index bytes disjoint from that packet.
 * The window begins at byte 3+4*sub / bit 4+sub and ends within byte 19.
 * This is a C-only bounded packet reader, not a generic SpeexBits API.
 * Keep generic partial-read/overflow helpers separate from this trusted map. */
#ifndef SPEEX_NB3_SUBFRAME_H
#define SPEEX_NB3_SUBFRAME_H
#include "speex_platform.h"

static SPEEX_NB3_STAGE_O2 uint16_t speex_nb3_unpack_subframe(
    const uint8_t *packet, uint8_t sub, uint8_t indices[4])
{
    const uint8_t *p=packet+3+4*sub;
    const uint8_t a=p[0],b=p[1],c=p[2],d=p[3],e=p[4];
    switch (sub) {
    case 0:
        indices[0]=(c>>2)&31;
        indices[1]=((c&3)<<3)|(d>>5);
        indices[2]=d&31;indices[3]=e>>3;
        return ((uint16_t)(a&15)<<9)|((uint16_t)b<<1)|(c>>7);
    case 1:
        indices[0]=(c>>1)&31;
        indices[1]=((c&1)<<4)|(d>>4);
        indices[2]=((d&15)<<1)|(e>>7);indices[3]=(e>>2)&31;
        return ((uint16_t)(a&7)<<10)|((uint16_t)b<<2)|(c>>6);
    case 2:
        indices[0]=c&31;indices[1]=d>>3;
        indices[2]=((d&7)<<2)|(e>>6);indices[3]=(e>>1)&31;
        return ((uint16_t)(a&3)<<11)|((uint16_t)b<<3)|(c>>5);
    case 3:
        indices[0]=((c&15)<<1)|(d>>7);indices[1]=(d>>2)&31;
        indices[2]=((d&3)<<3)|(e>>5);indices[3]=e&31;
        return ((uint16_t)(a&1)<<12)|((uint16_t)b<<4)|(c>>4);
    }
    return 0; /* Unreachable for the validated four-subframe controller. */
}
#endif
