#ifndef MICROMUSIC_ATTINY88_WAVE_READER_H
#define MICROMUSIC_ATTINY88_WAVE_READER_H
#include <stdint.h>
#if defined(__AVR__)
#include <avr/io.h>
#include <avr/pgmspace.h>
#endif

/* Hardware memory access is separate from the synthesis arithmetic.
 * Default: the manufacturer's C Flash-access API. Explicitly enable the
 * optional ATtiny88 ASM path with -DMICROMUSIC_WAVE_READ_ASM=1.
 * Preconditions: index is inside the bank; AVR address fits near Flash.
 * This C-callable interface uses the compiler ABI, not the firmware's private
 * live-Z/Carry contract. Its cycle count depends on compiler allocation. */
static inline uint8_t micromusic_wave_byte(const uint8_t *bank, uint8_t index)
{
    const uint8_t *address = bank + index;
#if defined(__AVR_ATtiny88__) && defined(MICROMUSIC_WAVE_READ_ASM) && MICROMUSIC_WAVE_READ_ASM
    uint8_t sample;
    __asm__ __volatile__("lpm %0,Z" : "=r" (sample) : "z" (address) : "memory");
    return sample;
#elif defined(__AVR__)
    return pgm_read_byte_near(address);
#else
    return *address;
#endif
}
#endif
