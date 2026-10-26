/* Generated narrow-sum specialization; same portable analysis interface. */
#define codec2_analysis_forward codec2_analysis_fast_forward
/* Project reuse of the independently qualified integer weighted-spectrum C.
 * Main and gamma-weighted spectra have independent precision settings.
 * KISS BSD provenance and conditions remain in fixed_weight.c/tables.
 */
#include "fixed_analysis.h"
#ifndef CODEC2_ANALYSIS_BITS
#define CODEC2_ANALYSIS_BITS 32
#endif
#ifndef CODEC2_ANALYSIS_TWIDDLE_Q
#define CODEC2_ANALYSIS_TWIDDLE_Q 30
#endif
#ifndef CODEC2_ANALYSIS_DIRECT_PAIR
#define CODEC2_ANALYSIS_DIRECT_PAIR 1
#endif
#ifndef CODEC2_ANALYSIS_CHECKS
#define CODEC2_ANALYSIS_CHECKS 0
#endif
#undef CODEC2_WEIGHT_BITS
#undef CODEC2_WEIGHT_TWIDDLE_Q
#undef CODEC2_WEIGHT_DIRECT_PAIR
#undef CODEC2_WEIGHT_CHECKS
#undef CODEC2_WEIGHT_SPLIT24
#undef CODEC2_WEIGHT_AVR_INT24
#undef CODEC2_WEIGHT_ROUND_LEGACY
#define CODEC2_WEIGHT_BITS CODEC2_ANALYSIS_BITS
#define CODEC2_WEIGHT_TWIDDLE_Q CODEC2_ANALYSIS_TWIDDLE_Q
#define CODEC2_WEIGHT_DIRECT_PAIR CODEC2_ANALYSIS_DIRECT_PAIR
#define CODEC2_WEIGHT_CHECKS CODEC2_ANALYSIS_CHECKS
#define CODEC2_WEIGHT_SPLIT24 0
#define CODEC2_WEIGHT_AVR_INT24 0
#define CODEC2_WEIGHT_ROUND_LEGACY 0
#define codec2_weight codec2_analysis_context
#define codec2_weight_init codec2_analysis_init
#define codec2_weight_dc codec2_analysis_dc
#define codec2_weight_pair codec2_analysis_pair
#include "fixed_weight_sums32.c"

void codec2_analysis_forward(compact_transform *buffer,const float coefficients[11]){
    codec2_analysis_context state;codec2_analysis_init(&state,coefficients);
    buffer->frequency[0]=codec2_analysis_dc(&state);
    int32_t nyquist=0;
    for(unsigned i=0;i<11;++i)nyquist=(i&1)?weight_sub32(nyquist,state.coefficient[i]):weight_add32(nyquist,state.coefficient[i]);
    buffer->frequency[256].r=ldexpf((float)checked32(nyquist),state.exponent);
    buffer->frequency[256].i=0;
    for(unsigned k=1;k<=128;++k){
        compact_complex positive,negative;codec2_analysis_pair(&state,k,&positive,&negative);
        buffer->frequency[k]=positive;buffer->frequency[256-k]=negative;
    }
}
