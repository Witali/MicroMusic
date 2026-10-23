/* Restricted <=7-bit fields, MSB first. API-compatible reader for NB3. */
#include <stdint.h>
#include "speex/speex_bits.h"
__attribute__((noinline))
unsigned int speex_bits_unpack_unsigned(SpeexBits *bits, int nbBits)
{
    uint8_t n = (uint8_t)nbBits;
    uint8_t offset = (uint8_t)bits->bitPtr;
    uint8_t position = (uint8_t)bits->charPtr;
    uint8_t end = offset + n;
    uint8_t byte;
    if (nbBits < 1 || nbBits > 7 || bits->overflow ||
        (unsigned)position * 8 + end > (unsigned)bits->nbBits) {
        bits->overflow = 1;
        return 0;
    }
    byte = (uint8_t)((uint8_t)bits->chars[position] << offset);
    if (end > 8) byte |= (uint8_t)bits->chars[position+1] >> (8-offset);
    bits->charPtr = position + (end >> 3);
    bits->bitPtr = end & 7;
    return byte >> (8-n);
}
