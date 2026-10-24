/* Explicit byte representation; independent of CPU endianness and alignment.
 * Values are signed24, represented with the least-significant byte first.
 * Do not allocate a three-byte type with the power-of-two scratch allocator. */
#ifndef MICROMUSIC_PACKED24_H
#define MICROMUSIC_PACKED24_H
#include <stdint.h>
static inline int32_t speex_nb3_read24(const uint8_t *p)
{
    uint32_t bits=(uint32_t)p[0] | ((uint32_t)p[1]<<8) | ((uint32_t)p[2]<<16);
    return (int32_t)(bits<<8)>>8;
}
static inline void speex_nb3_write24(uint8_t *p,int32_t value)
{
    p[0]=(uint8_t)value;
    p[1]=(uint8_t)((uint32_t)value>>8);
    p[2]=(uint8_t)((uint32_t)value>>16);
}
#endif
