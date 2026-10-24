/* Four consecutive unsigned five-bit NB3 innovation indices, MSB first.
 * Private bounded batch; the public generic reader retains its API/semantics.
 * Valid NB3 subframe index blocks start at offsets 1,2,3,4 and fit three bytes.
 * The fallback preserves partial reads and sticky overflow for other states. */
#ifndef MICROMUSIC_NB3_INDICES_H
#define MICROMUSIC_NB3_INDICES_H
#include "speex_platform.h"
#include "speex/speex_bits.h"
static SPEEX_NB3_HOT SPEEX_NB3_NOINLINE void speex_nb3_unpack_indices(
    SpeexBits *bits,uint8_t indices[4])
{
    const uint8_t offset=(uint8_t)bits->bitPtr;
    const uint8_t position=(uint8_t)bits->charPtr;
    const uint8_t end=offset+20;
    if (offset>4 || bits->overflow ||
        (unsigned)position*8+end>(unsigned)bits->nbBits) {
        for (uint8_t i=0;i<4;i++)
            indices[i]=(uint8_t)speex_bits_unpack_unsigned(bits,5);
        return;
    }
    const uint8_t a=(uint8_t)bits->chars[position];
    const uint8_t b=(uint8_t)bits->chars[position+1];
    const uint8_t c=(uint8_t)bits->chars[position+2];
    const uint16_t hi=(((uint16_t)a<<8)|b)>>(6-offset);
    const uint16_t lo=(((uint16_t)b<<8)|c)>>(4-offset);
    indices[0]=(uint8_t)((hi>>5)&31);
    indices[1]=(uint8_t)(hi&31);
    indices[2]=(uint8_t)((lo>>5)&31);
    indices[3]=(uint8_t)(lo&31);
    bits->charPtr=position+(end>>3);
    bits->bitPtr=end&7;
}
#endif
