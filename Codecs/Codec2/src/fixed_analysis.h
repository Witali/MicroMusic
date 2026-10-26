/* Portable fixed-point main LPC spectrum; no heap or mutable global state. */
#ifndef MICROMUSIC_CODEC2_FIXED_ANALYSIS_H
#define MICROMUSIC_CODEC2_FIXED_ANALYSIS_H
#include "compact_fft.h"
void codec2_analysis_forward(compact_transform *buffer,const float coefficients[11]);
#endif
