#pragma once
#include <stdint.h>
#define PROGMEM __attribute__((section(".progmem.data")))
#define pgm_read_word(p) (*(const uint16_t*)(p))
#define pgm_read_byte_near(p) (*(const uint8_t*)(p))
