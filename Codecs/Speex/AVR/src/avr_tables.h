#ifndef MICROMUSIC_AVR_TABLES_H
#define MICROMUSIC_AVR_TABLES_H
#include <stdint.h>
#include "speex_platform.h"
#ifndef SPEEX_NB3_TABLE
#ifdef __AVR__
#include <avr/pgmspace.h>
#define SPEEX_NB3_TABLE PROGMEM
#define SPEEX_NB3_READ_I8(p) ((int8_t)pgm_read_byte(p))
#define SPEEX_NB3_READ_I16(p) ((int16_t)pgm_read_word(p))
#define SPEEX_NB3_READ_I32(p) ((int32_t)pgm_read_dword(p))
#else
#define SPEEX_NB3_TABLE
#define SPEEX_NB3_READ_I8(p) (*(const int8_t *)(p))
#define SPEEX_NB3_READ_I16(p) (*(const int16_t *)(p))
#define SPEEX_NB3_READ_I32(p) (*(const int32_t *)(p))
#endif
#endif
#if !defined(SPEEX_NB3_READ_I8) || !defined(SPEEX_NB3_READ_I16) || !defined(SPEEX_NB3_READ_I32)
#error Custom table placement requires all three signed read macros
#endif
#define AVR_TABLE SPEEX_NB3_TABLE
#define AVR_READ_I8(p) SPEEX_NB3_READ_I8(p)
#define AVR_READ_I16(p) SPEEX_NB3_READ_I16(p)
#define AVR_READ_I32(p) SPEEX_NB3_READ_I32(p)
#endif
