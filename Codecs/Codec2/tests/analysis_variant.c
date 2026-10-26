#include "codec2_hybrid.h"
#include "compact_fft.h"
void codec2_analysis_probe(compact_transform *buffer,const float coefficients[11]);
#define codec2_hybrid_init codec2_analysis_candidate_init
#define codec2_hybrid_decode codec2_analysis_candidate_decode
#define compact_forward_lpc codec2_analysis_probe
#include "../src/spectral_decoder.c"
