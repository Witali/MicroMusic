/* Portable C block-floating inverse-FFT candidate. Not a real-time admission. */
#ifndef MICROMUSIC_CODEC2_FIXED_INVERSE_H
#define MICROMUSIC_CODEC2_FIXED_INVERSE_H
#include "compact_fft.h"

/* Select at build time: component precision 8/16/24/32, twiddle Q6 through Q14.
 * Default: 16-bit components, Q9 twiddles, no wide final stage. Host precision
 * studies enable CODEC2_FIXED_CHECKS=1 to check every narrowed intermediate.
 * 24-bit components use int32_t storage in portable C. No handwritten ASM.
 * Input is the finite 257-bin Codec2 synthesis spectrum; output 512 real floats.
 * Reuses the same buffer; compile with -fno-strict-aliasing.
 */
void codec2_fixed_inverse(compact_transform *buffer);
#endif
