#ifndef MICROMUSIC_STORAGE_H
#define MICROMUSIC_STORAGE_H
#include <stdint.h>
#ifdef __AVR__
#include <avr/pgmspace.h>
#define UM_READ(a) pgm_read_byte((const void *)(uintptr_t)(a))
#define UM_CONST PROGMEM
#define UM_VALUE(a,i) pgm_read_byte(&(a)[i])
#else
extern const uint8_t *um_image;
#define UM_READ(a) (um_image[(uint16_t)(a)])
#define UM_CONST
#define UM_VALUE(a,i) ((a)[i])
#endif
static inline uint16_t um_word(uint16_t address) {
    uint8_t lo=UM_READ(address);
    return lo | ((uint16_t)UM_READ(address+1)<<8);
}
#endif
