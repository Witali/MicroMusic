/* Both native backends in one process for frame-by-frame RNG control evidence. */
#include "codec2_hybrid.h"
#define codec2_hybrid_init codec2_postfilter_init
#define codec2_hybrid_decode codec2_postfilter_decode
#include "../src/hybrid_postfilter.c"
