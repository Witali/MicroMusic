/* Read pinned binary32 table bits; hardware access stays outside arithmetic. */
#ifndef MICROMUSIC_CODEC2_ANALYSIS_TABLE_ACCESS_H
#define MICROMUSIC_CODEC2_ANALYSIS_TABLE_ACCESS_H
#include "table_access.h"
#include <string.h>
static uint32_t codec2_analysis_table_bits(const float *table,unsigned index){
#if defined(__AVR__)
    return pgm_read_dword(&table[index]);
#else
    uint32_t value;memcpy(&value,&table[index],4);return value;
#endif
}
#endif
