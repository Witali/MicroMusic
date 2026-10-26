/* Hardware memory access, independent of arithmetic backend selection. */
#ifndef MICROMUSIC_CODEC2_TABLE_ACCESS_H
#define MICROMUSIC_CODEC2_TABLE_ACCESS_H
#include <stdint.h>
#if defined(__AVR__)
#include <avr/pgmspace.h>
#define CODEC2_TABLE_STORAGE PROGMEM
#define CODEC2_TABLE_WORD(table, index) pgm_read_word(&(table)[index])
#else
#define CODEC2_TABLE_STORAGE
#define CODEC2_TABLE_WORD(table, index) ((table)[index])
#endif
#endif
