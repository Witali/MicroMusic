#include "codec2_hybrid.h"
#define codec2_hybrid_init codec2_postfilter_init
#define codec2_hybrid_decode codec2_postfilter_decode
#include "../src/spectral_decoder.c"
