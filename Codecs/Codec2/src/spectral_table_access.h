/* Device address-space reads are independent of arithmetic precision. */
#ifndef MICROMUSIC_CODEC2_SPECTRAL_TABLE_ACCESS_H
#define MICROMUSIC_CODEC2_SPECTRAL_TABLE_ACCESS_H
#include "fixed_table_access.h"
#if defined(__AVR__)
#define CODEC2_TABLE_DWORD(table,index) pgm_read_dword(&(table)[index])
#else
#define CODEC2_TABLE_DWORD(table,index) ((table)[index])
#endif
#endif
