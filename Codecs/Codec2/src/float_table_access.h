/* Flash address-space access stays separate from the C arithmetic backend. */
#ifndef MICROMUSIC_CODEC2_FLOAT_TABLE_ACCESS_H
#define MICROMUSIC_CODEC2_FLOAT_TABLE_ACCESS_H
#include "table_access.h"
#if defined(__AVR__)
#define CODEC2_TABLE_FLOAT(table, index) pgm_read_float(&(table)[index])
#else
#define CODEC2_TABLE_FLOAT(table, index) ((table)[index])
#endif
#endif
