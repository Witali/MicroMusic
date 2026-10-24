/* Restricted NB3 subframe header: unsigned pitch(7), gain(5), energy(1).
 * Valid headers start at offsets 4..7 and fit three bytes. Return the packed
 * thirteen-bit value; preserve partial/sticky overflow through generic reads. */
#ifndef MICROMUSIC_NB3_HEADER_H
#define MICROMUSIC_NB3_HEADER_H
#include "speex_platform.h"
#include "speex/speex_bits.h"
static SPEEX_NB3_ALWAYS_INLINE uint16_t speex_nb3_unpack_header(SpeexBits *bits)
{
    const uint8_t offset=(uint8_t)bits->bitPtr;
    const uint8_t position=(uint8_t)bits->charPtr;
    const uint8_t end=offset+13;
    if ((uint8_t)(offset-4)>3 || bits->overflow ||
        (unsigned)position*8+end>(unsigned)bits->nbBits) {
        const unsigned pitch=speex_bits_unpack_unsigned(bits,7);
        const unsigned gain=speex_bits_unpack_unsigned(bits,5);
        const unsigned energy=speex_bits_unpack_unsigned(bits,1);
        return (uint16_t)((pitch<<6)|(gain<<1)|energy);
    }
    const uint8_t a=(uint8_t)bits->chars[position];
    const uint8_t b=(uint8_t)bits->chars[position+1];
    const uint8_t c=(uint8_t)bits->chars[position+2];
    const uint16_t ab=((uint16_t)a<<8)|b;
    const uint16_t value=(uint16_t)(ab<<(offset-3))|(uint16_t)(c>>(11-offset));
    bits->charPtr=position+(end>>3);
    bits->bitPtr=end&7;
    return value&8191;
}
#endif
