#!/usr/bin/env python3
"""Preserve the paired graph while replacing proven narrow sums and averages."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def generate_weight():
    body=(ROOT/'src/fixed_weight.c').read_text(encoding='utf-8')
    at='typedef struct {codec2_weight_component r,i;} complex_fixed;'
    addition='''
#if !CODEC2_WEIGHT_DIRECT_PAIR || CODEC2_WEIGHT_SPLIT24 || CODEC2_WEIGHT_AVR_INT24 || CODEC2_WEIGHT_ROUND_LEGACY
#error Narrow-sum profile requires the direct paired graph, int32 storage and ordinary int64 products
#endif
#include "weight_sum32.h"
static codec2_weight_component checked32(int32_t value){
#if CODEC2_WEIGHT_CHECKS
    assert((int64_t)value>=-(INT64_C(1)<<(CODEC2_WEIGHT_BITS-1))&&(int64_t)value<(INT64_C(1)<<(CODEC2_WEIGHT_BITS-1)));
#endif
    return (codec2_weight_component)value;
}
'''
    assert body.count(at)==1;body=body.replace(at,at+addition)
    # Keep the old unused radix helpers intact. All replacements below select
    # only the paired path; wide product accumulation/rounding remains unchanged.
    body=body.replace('checked(rounded((int64_t)a.r*b.r','checked32(rounded((int64_t)a.r*b.r')
    body=body.replace('checked(rounded((int64_t)a.r*b.i','checked32(rounded((int64_t)a.r*b.i')
    body=body.replace('s->coefficient[i]=checked((int32_t)','s->coefficient[i]=checked32((int32_t)')
    old='int64_t sum=0;for(unsigned i=0;i<11;++i)sum+=s->coefficient[i];compact_complex out={ldexpf((float)checked(sum),s->exponent),0};return out;'
    new='int32_t sum=0;for(unsigned i=0;i<11;++i)sum=weight_add32(sum,s->coefficient[i]);compact_complex out={ldexpf((float)checked32(sum),s->exponent),0};return out;'
    assert body.count(old)==1;body=body.replace(old,new)
    for field,op,rhs in [('a.r','+','rounded(rr-ii,CODEC2_WEIGHT_TWIDDLE_Q)'),('b.r','+','rounded(rr+ii,CODEC2_WEIGHT_TWIDDLE_Q)'),('a.i','+','rounded(ri+ir,CODEC2_WEIGHT_TWIDDLE_Q)'),('b.i','+','rounded(ir-ri,CODEC2_WEIGHT_TWIDDLE_Q)'),('a.r','+','lr'),('b.r','+','lr'),('a.i','+','li'),('b.i','-','li')]:
        old=f'{field}=checked((int64_t){field}{op}{rhs})';new=f'{field}=checked32(weight_{"add" if op=="+" else "sub"}32({field},{rhs}))'
        assert body.count(old)==1,old;body=body.replace(old,new)
    replacements={
        'complex_fixed sum={checked((int64_t)a.r+b.r),checked((int64_t)a.i+b.i)};':'complex_fixed sum={checked32(weight_add32(a.r,b.r)),checked32(weight_add32(a.i,b.i))};',
        'complex_fixed difference={checked((int64_t)a.r-b.r),checked((int64_t)a.i-b.i)};':'complex_fixed difference={checked32(weight_sub32(a.r,b.r)),checked32(weight_sub32(a.i,b.i))};',
        'int32_t pr=checked(rounded((int64_t)sum.r+p.r,1)),pi=checked(rounded((int64_t)sum.i+p.i,1));':'int32_t pr=checked32(weight_half_sum32(sum.r,p.r)),pi=checked32(weight_half_sum32(sum.i,p.i));',
        'int32_t nr=checked(rounded((int64_t)sum.r-p.r,1)),ni=checked(rounded((int64_t)p.i-sum.i,1));':'int32_t nr=checked32(weight_half_difference32(sum.r,p.r)),ni=checked32(weight_half_difference32(p.i,sum.i));'}
    for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
    return ('/* Generated exact narrow sums for the paired C graph; original wide C remains selectable. */\n'+body).encode('utf-8')

def generate_fast():
    body=(ROOT/'src/fixed_analysis.c').read_text(encoding='utf-8').replace('#include "fixed_weight.c"','#include "fixed_weight_sums32.c"')
    old='int64_t nyquist=0;\n    for(unsigned i=0;i<11;++i)nyquist+=(i&1)?-(int64_t)state.coefficient[i]:state.coefficient[i];'
    new='int32_t nyquist=0;\n    for(unsigned i=0;i<11;++i)nyquist=(i&1)?weight_sub32(nyquist,state.coefficient[i]):weight_add32(nyquist,state.coefficient[i]);'
    assert body.count(old)==1;body=body.replace(old,new).replace('(float)checked(nyquist)','(float)checked32(nyquist)')
    return ('/* Generated narrow-sum specialization; same portable analysis interface. */\n#define codec2_analysis_forward codec2_analysis_fast_forward\n'+body).encode('utf-8')
if __name__=='__main__':
    (ROOT/'src/fixed_weight_sums32.c').write_bytes(generate_weight());(ROOT/'src/fast_analysis_sums32.c').write_bytes(generate_fast())
