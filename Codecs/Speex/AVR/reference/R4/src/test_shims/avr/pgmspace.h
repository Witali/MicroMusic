#ifndef AVR_PGMSPACE_H
#define AVR_PGMSPACE_H
#include <stdint.h>
#define PROGMEM __attribute__((section(".progmem.data")))
static inline uint8_t pgm_read_byte(const void *p) { uint8_t x; __asm__ volatile("lpm %0, Z" : "=r"(x) : "z"(p)); return x; }
static inline uint16_t pgm_read_word(const void *p) { uint16_t r; const uint8_t *b=(const uint8_t*)p; r=pgm_read_byte(b); r|=((uint16_t)pgm_read_byte(b+1))<<8; return r; }
static inline uint32_t pgm_read_dword(const void *p) { uint32_t r=0; const uint8_t *b=(const uint8_t*)p; for(uint8_t i=0;i<4;i++)r|=((uint32_t)pgm_read_byte(b+i))<<(8*i);return r; }
#endif
