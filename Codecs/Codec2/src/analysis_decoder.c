/* Explicit whole-decoder specialization: both LPC spectra are fixed-point.
 * Phase, power normalization and other remaining stages still use float.
 * Codec2 LGPL notices and all stages are retained in spectral_decoder.c.
 */
#include "fixed_analysis.h"
#define compact_forward_lpc codec2_analysis_forward
#include "spectral_decoder.c"
