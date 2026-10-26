/* Explicit C specialization of the one fixed 0.2f postfilter power call.
 * Float/previous hybrid fallback remains available by selecting hybrid_decoder.c.
 */
#include <math.h>
#include "fixed_fifth.h"
#ifdef powf
#undef powf
#endif
#define powf(value, exponent) codec2_fixed_fifth(value)
#include "hybrid_decoder.c"
