/*
Copyright (c) 2003-2010, Mark Borgerding
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:
 * Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
 * Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
 * Neither the author nor the names of any contributors may be used to endorse
   or promote products derived from this software without specific prior
   written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
OF THE POSSIBILITY OF SUCH DAMAGE.
*/
/* In-place sparse fixed LPC FFT. The original scalar radix-four rounding graph
 * is retained, sharing all four sibling bins instead of reevaluating each pair.
 * KISS provenance/BSD conditions are retained with included table data and the
 * original compact_fft.c. The adaptive faithful path remains a separate C path.
 */
#include "fixed_analysis.h"
#ifndef CODEC2_ANALYSIS_BITS
#define CODEC2_ANALYSIS_BITS 32
#endif
#ifndef CODEC2_ANALYSIS_TWIDDLE_Q
#define CODEC2_ANALYSIS_TWIDDLE_Q 30
#endif
#ifndef CODEC2_ANALYSIS_CHECKS
#define CODEC2_ANALYSIS_CHECKS 0
#endif
#if CODEC2_ANALYSIS_BITS !=32 || CODEC2_ANALYSIS_TWIDDLE_Q !=30
#error This matrix profile is qualified only for 32-bit data and Q30 twiddles
#endif
#undef CODEC2_WEIGHT_BITS
#undef CODEC2_WEIGHT_TWIDDLE_Q
#undef CODEC2_WEIGHT_DIRECT_PAIR
#undef CODEC2_WEIGHT_CHECKS
#undef CODEC2_WEIGHT_SPLIT24
#undef CODEC2_WEIGHT_AVR_INT24
#undef CODEC2_WEIGHT_ROUND_LEGACY
#define CODEC2_WEIGHT_BITS 32
#define CODEC2_WEIGHT_TWIDDLE_Q 30
#define CODEC2_WEIGHT_DIRECT_PAIR 1
#define CODEC2_WEIGHT_CHECKS CODEC2_ANALYSIS_CHECKS
#define CODEC2_WEIGHT_SPLIT24 0
#define CODEC2_WEIGHT_AVR_INT24 0
#define CODEC2_WEIGHT_ROUND_LEGACY 0
#define codec2_weight codec2_matrix_context
#define codec2_weight_init codec2_matrix_init
#define codec2_weight_dc codec2_matrix_dc
#define codec2_weight_pair codec2_matrix_pair
#include "fixed_weight_sums32.c"
typedef char matrix_component_size[(sizeof(complex_fixed)==8)?1:-1];
typedef char matrix_buffer_size[(sizeof(compact_transform)==257*8)?1:-1];
#if defined(__GNUC__) || defined(__clang__)
#define MATRIX_INLINE static inline __attribute__((always_inline))
#else
#define MATRIX_INLINE static inline
#endif
MATRIX_INLINE complex_fixed load(const compact_transform *buffer,unsigned index){complex_fixed x;memcpy(&x,(const unsigned char *)buffer+index*8,8);return x;}
MATRIX_INLINE void store(compact_transform *buffer,unsigned index,complex_fixed x){memcpy((unsigned char *)buffer+index*8,&x,8);}
MATRIX_INLINE complex_fixed plus(complex_fixed a,complex_fixed b){complex_fixed x={checked32(weight_add32(a.r,b.r)),checked32(weight_add32(a.i,b.i))};return x;}
MATRIX_INLINE complex_fixed minus(complex_fixed a,complex_fixed b){complex_fixed x={checked32(weight_sub32(a.r,b.r)),checked32(weight_sub32(a.i,b.i))};return x;}
static complex_fixed child(complex_fixed a,complex_fixed b,unsigned j,unsigned which){
    complex_fixed p=multiply(b,twiddle(4*j,0)),out;
    if(which==0)out=plus(a,p);else if(which==2)out=minus(a,p);
    else if(which==1){out.r=checked32(weight_add32(a.r,p.i));out.i=checked32(weight_sub32(a.i,p.r));}
    else{out.r=checked32(weight_sub32(a.r,p.i));out.i=checked32(weight_add32(a.i,p.r));}return out;
}
void codec2_analysis_fast_forward(compact_transform *buffer,const float coefficients[11]){
    codec2_matrix_context state;codec2_matrix_init(&state,coefficients);
    {
        complex_fixed c0={state.coefficient[0],state.coefficient[1]},c1={state.coefficient[2],state.coefficient[3]},c2={state.coefficient[4],state.coefficient[5]},c3={state.coefficient[6],state.coefficient[7]},c4={state.coefficient[8],state.coefficient[9]},c5={state.coefficient[10],0};
        for(unsigned j=0;j<64;++j){store(buffer,j,child(c0,c4,j&15,j>>4));store(buffer,j+64,child(c1,c5,j&15,j>>4));store(buffer,j+128,c2);store(buffer,j+192,c3);}
    }
    for(unsigned j=0;j<64;++j){
        complex_fixed a=load(buffer,j),b=multiply(load(buffer,j+64),twiddle(j,0)),c=multiply(load(buffer,j+128),twiddle(2*j,0)),d=multiply(load(buffer,j+192),twiddle(3*j,0));
        complex_fixed ep=plus(a,c),em=minus(a,c),op=plus(b,d),om=minus(b,d),first={checked32(weight_add32(em.r,om.i)),checked32(weight_sub32(em.i,om.r))},last={checked32(weight_sub32(em.r,om.i)),checked32(weight_add32(em.i,om.r))};
        store(buffer,j,plus(ep,op));store(buffer,j+128,minus(ep,op));store(buffer,j+64,first);store(buffer,j+192,last);
    }
    {
        complex_fixed dc=load(buffer,0),zero={checked32(weight_add32(dc.r,dc.i)),0},nyquist={checked32(weight_sub32(dc.r,dc.i)),0};store(buffer,0,zero);store(buffer,256,nyquist);
    }
    for(unsigned k=1;k<=128;++k){
        complex_fixed a=load(buffer,k),b=load(buffer,256-k);b.i=-b.i;complex_fixed sum=plus(a,b),difference=minus(a,b),p=multiply(difference,twiddle(k-1,1));
        complex_fixed positive={checked32(weight_half_sum32(sum.r,p.r)),checked32(weight_half_sum32(sum.i,p.i))},negative={checked32(weight_half_difference32(sum.r,p.r)),checked32(weight_half_difference32(p.i,sum.i))};store(buffer,k,positive);store(buffer,256-k,negative);
    }
    for(unsigned k=0;k<=256;++k){complex_fixed x=load(buffer,k);buffer->frequency[k].r=ldexpf((float)x.r,state.exponent);buffer->frequency[k].i=ldexpf((float)x.i,state.exponent);}
}
