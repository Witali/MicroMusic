/* Selective integer refinement of cancellation-sensitive LPC spectral pairs.
 * Both paths are C. The original faithful backend remains independently usable.
 * KISS copyright/BSD conditions are retained in the included implementation.
 */
#include "fixed_analysis.h"
#define codec2_analysis_forward codec2_analysis_faithful_reference
#include "faithful_analysis.c"
#undef codec2_analysis_forward
#include "compact_analysis_helpers.inc"
#ifndef CODEC2_ANALYSIS_GUARD_BITS
#define CODEC2_ANALYSIS_GUARD_BITS 14
#endif
#ifndef CODEC2_ADAPTIVE_STATS
#define CODEC2_ADAPTIVE_STATS 0
#endif
#if CODEC2_ANALYSIS_GUARD_BITS < 0 || CODEC2_ANALYSIS_GUARD_BITS > 30
#error Unsupported relative conditioning guard
#endif
void codec2_analysis_fast_forward(compact_transform *buffer,const float coefficients[11]);
#if CODEC2_ADAPTIVE_STATS
void codec2_adaptive_record(unsigned refined_bins);
#define REFINED(n) (refined+=(n))
#else
#define REFINED(n) ((void)0)
#endif
static int ill_conditioned(compact_complex value,uint32_t threshold){
    uint32_t r,i;memcpy(&r,&value.r,4);memcpy(&i,&value.i,4);
    r&=UINT32_C(0x7fffffff);i&=UINT32_C(0x7fffffff);
    return r<=threshold&&i<=threshold;
}
static void prepare(faithful_context *state,const float coefficients[11],int exponent){
    state->exponent=exponent-(CODEC2_FAITHFUL_BITS-3);
    for(unsigned i=0;i<11;++i){uint32_t bits;memcpy(&bits,&coefficients[i],4);state->a[i]=from_bits(bits,state->exponent);}
}
/* Keep only sum and product alive across scalar stores, rather than storing
 * five wide intermediate complex structs and both wide result structs. */
static void refine_pair(compact_transform *buffer,const faithful_context *state,unsigned k){
    faithful_complex a=compact_spectrum(state,k),b=compact_spectrum(state,256-k);b.i=-b.i;
    int64_t ar=a.r,ai=a.i;
    a.r=add(ar,b.r);a.i=add(ai,b.i);b.r=sub(ar,b.r);b.i=sub(ai,b.i);
    b=multiply(b,twiddle(k-1,1));
    buffer->frequency[k].r=ldexpf((float)half(add(a.r,b.r)),state->exponent);
    buffer->frequency[k].i=ldexpf((float)half(add(a.i,b.i)),state->exponent);
    buffer->frequency[256-k].r=ldexpf((float)half(sub(a.r,b.r)),state->exponent);
    buffer->frequency[256-k].i=ldexpf((float)half(sub(b.i,a.i)),state->exponent);
}
void codec2_analysis_forward(compact_transform *buffer,const float coefficients[11]){
    codec2_analysis_fast_forward(buffer,coefficients);
    float total=0;for(unsigned i=0;i<11;++i)total+=fabsf(coefficients[i]);
    int exponent;frexpf(total,&exponent);
    int threshold_exponent=exponent-CODEC2_ANALYSIS_GUARD_BITS;
#if CODEC2_ANALYSIS_CHECKS
    assert(threshold_exponent>=-126&&threshold_exponent<=127);
#endif
    uint32_t threshold=(uint32_t)(threshold_exponent+127)<<23;
    faithful_context state;int ready=0;
#if CODEC2_ADAPTIVE_STATS
    unsigned refined=0;
#endif
    if(ill_conditioned(buffer->frequency[0],threshold)||ill_conditioned(buffer->frequency[256],threshold)){
        prepare(&state,coefficients,exponent);ready=1;faithful_complex dc=compact_spectrum(&state,0);
        buffer->frequency[0].r=ldexpf((float)add(dc.r,dc.i),state.exponent);buffer->frequency[0].i=0;
        buffer->frequency[256].r=ldexpf((float)sub(dc.r,dc.i),state.exponent);buffer->frequency[256].i=0;REFINED(2);
    }
    for(unsigned k=1;k<=128;++k){
        if(!ill_conditioned(buffer->frequency[k],threshold)&&!ill_conditioned(buffer->frequency[256-k],threshold))continue;
        if(!ready){prepare(&state,coefficients,exponent);ready=1;}
        refine_pair(buffer,&state,k);REFINED(k==128?1:2);
    }
#if CODEC2_ADAPTIVE_STATS
    codec2_adaptive_record(refined);
#endif
}
