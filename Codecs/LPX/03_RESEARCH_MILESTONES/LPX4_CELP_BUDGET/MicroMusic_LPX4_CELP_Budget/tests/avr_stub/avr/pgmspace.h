#pragma once
#include <stdint.h>
#define PROGMEM __attribute__((section(".progmem.data")))
/* Test-only stub for AVR Clang compiler if avr-libc is missing.
 * These are proper AVR LPM instructions; NOT a complete avr-libc replacement.
 */
static __inline__ uint8_t pgm_read_byte(const void *p) {
    uint8_t out;
    __asm__ __volatile__("lpm %0, Z" : "=r"(out) : "z"(p));
    return out;
}
static __inline__ uint16_t pgm_read_word(const void *p) {
    uint8_t lo, hi;
    __asm__ __volatile__("lpm %0, Z+\n\tlpm %1, Z" : "=&r"(lo), "=&r"(hi) : "z"(p));
    return (uint16_t)lo | ((uint16_t)hi<<8);
}
