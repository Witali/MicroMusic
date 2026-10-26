/* LGPL-2.1, see vendor/codec2-1.2.0/COPYING. */
#ifndef MICROMUSIC_CODEC2_LPC_H
#define MICROMUSIC_CODEC2_LPC_H
#include <stdint.h>

/* Convert ten LSP angles to eleven LPC coefficients, a[0] = 1<<23.
 * Input unit: 12.5 Hz at 8 kHz sampling, angle = input*pi/320.
 * This exactly represents current 25-Hz codebooks and midpoint interpolation
 * between such frames. Initialization LSPs may require separate quantization.
 * Non-null, non-overlapping arrays required. No heap or global mutable state.
 * Full order ten, including the last four LSPs. Portable integer C backend.
 * Q15 cosine LUT and Q23 polynomials; this is an approximation of upstream
 * float LSP->LPC, not a waveform decoder or a claim of sample-identical PCM.
 */
void codec2_lsp_to_lpc_q23(const uint16_t lsp_12p5hz[10], int32_t coefficients[11]);
#endif
