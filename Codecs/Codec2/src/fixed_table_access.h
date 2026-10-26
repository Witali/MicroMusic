/* Device memory access is independent of arithmetic precision/backend. */
#ifndef MICROMUSIC_CODEC2_FIXED_TABLE_ACCESS_H
#define MICROMUSIC_CODEC2_FIXED_TABLE_ACCESS_H
#include "table_access.h"
#if defined(__AVR__)
#define CODEC2_TABLE_BYTE(table, index) pgm_read_byte(&(table)[index])
#else
#define CODEC2_TABLE_BYTE(table, index) ((table)[index])
#endif
#endif
