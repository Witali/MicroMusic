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
/* Project block-floating adaptation of the pinned KISS sparse radix/real graph.
 * All spectral arithmetic is integer. A common block scale plus explicit
 * 24-significand rounding retains the original binary32 operation boundaries.
 * Original KISS copyright/BSD conditions accompany compact_tables.inc.
 */
#include "fixed_analysis.h"
#include "analysis_table_access.h"
#include "compact_tables.inc"
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
#if FLT_RADIX != 2 || FLT_MANT_DIG != 24
#error This boundary requires IEEE binary32
#endif
typedef char faithful_binary32_size[(sizeof(float)==4)?1:-1];
#ifndef CODEC2_FAITHFUL_BITS
#define CODEC2_FAITHFUL_BITS 48
#endif
#ifndef CODEC2_ANALYSIS_CHECKS
#define CODEC2_ANALYSIS_CHECKS 0
#endif
#if CODEC2_FAITHFUL_BITS < 24 || CODEC2_FAITHFUL_BITS > 56
#error Supported block width is 24..56 bits
#endif
typedef struct {int64_t r,i;} faithful_complex;
typedef struct {int64_t a[11];int exponent;} faithful_context;
typedef struct {uint32_t r,i;} faithful_twiddle;

static unsigned bit_length(uint64_t value){
    uint32_t high=(uint32_t)(value>>32),word=high?high:(uint32_t)value;unsigned bits=high?32:0;
    if(word>>16){word>>=16;bits+=16;}if(word>>8){word>>=8;bits+=8;}
    if(word>>4){word>>=4;bits+=4;}if(word>>2){word>>=2;bits+=2;}
    if(word>>1){word>>=1;bits+=1;}return bits+(word!=0);
}
/* Magnitudes only; ties to even. Inputs here never approach 2^63. */
static uint64_t round_shift(uint64_t value,unsigned shift){
    if(!shift)return value;if(shift>=64)return 0;
    uint64_t result=value>>shift,mask=(UINT64_C(1)<<shift)-1,half=UINT64_C(1)<<(shift-1),tail=value&mask;
    return result+(tail>half||(tail==half&&(result&1)));
}
static uint64_t magnitude(int64_t value){return value<0?UINT64_C(0)-(uint64_t)value:(uint64_t)value;}
static int64_t checked(int64_t value){
#if CODEC2_ANALYSIS_CHECKS
    assert(value>=-(INT64_C(1)<<(CODEC2_FAITHFUL_BITS-1))&&value<(INT64_C(1)<<(CODEC2_FAITHFUL_BITS-1)));
#endif
    return value;
}
static int64_t precision(int64_t value){
    uint64_t absolute=magnitude(value);unsigned bits=bit_length(absolute),shift=bits>24?bits-24:0;
    uint64_t result=round_shift(absolute,shift)<<shift;
    return checked(value<0?-(int64_t)result:(int64_t)result);
}
static int64_t add(int64_t a,int64_t b){return precision(a+b);}
static int64_t sub(int64_t a,int64_t b){return precision(a-b);}
static int64_t from_bits(uint32_t bits,int block_exponent){
    unsigned field=(bits>>23)&255;uint32_t mantissa=(bits&UINT32_C(0x7fffff))|(field?UINT32_C(0x800000):0);
    int shift=(field?(int)field-150:-149)-block_exponent;
    uint64_t result=shift>=0?(uint64_t)mantissa<<shift:round_shift(mantissa,(unsigned)-shift);
    return checked(bits>>31?-(int64_t)result:(int64_t)result);
}
static int64_t product(int64_t a,uint32_t factor){
    unsigned field=(factor>>23)&255;uint32_t mantissa=(factor&UINT32_C(0x7fffff))|(field?UINT32_C(0x800000):0);
    uint64_t absolute=magnitude(a);unsigned bits=bit_length(absolute),input_shift=bits>24?bits-24:0;
    uint32_t input=(uint32_t)(absolute>>input_shift);
#if CODEC2_ANALYSIS_CHECKS
    assert(((uint64_t)input<<input_shift)==absolute);
#endif
    uint64_t raw=(uint64_t)input*mantissa;unsigned width=bit_length(raw),shift=width>24?width-24:0;
    uint64_t rounded=round_shift(raw,shift);
    int align=(int)input_shift+(int)shift+(field?(int)field-150:-149);
    uint64_t result=align>=0?rounded<<align:round_shift(rounded,(unsigned)-align);
    return checked(((a<0)!=(factor>>31))?-(int64_t)result:(int64_t)result);
}
static faithful_twiddle twiddle(unsigned k,int super){
    faithful_twiddle w;
    w.r=codec2_analysis_table_bits(super?compact_super:compact_twiddle,2*k);
    w.i=codec2_analysis_table_bits(super?compact_super:compact_twiddle,2*k+1);return w;
}
static faithful_complex multiply(faithful_complex a,faithful_twiddle w){
    faithful_complex out={sub(product(a.r,w.r),product(a.i,w.i)),add(product(a.r,w.i),product(a.i,w.r))};return out;
}
static faithful_complex select_two(faithful_complex a,faithful_complex b,unsigned j,unsigned which){
    faithful_complex p=multiply(b,twiddle(4*j,0)),out;
    if(which==0){out.r=add(a.r,p.r);out.i=add(a.i,p.i);}
    else if(which==2){out.r=sub(a.r,p.r);out.i=sub(a.i,p.i);}
    else if(which==1){out.r=add(a.r,p.i);out.i=sub(a.i,p.r);}
    else{out.r=sub(a.r,p.i);out.i=add(a.i,p.r);}return out;
}
static faithful_complex spectrum(const faithful_context *s,unsigned bin){
    unsigned low=bin&63;faithful_complex c0={s->a[0],s->a[1]},c1={s->a[2],s->a[3]},c2={s->a[4],s->a[5]},c3={s->a[6],s->a[7]},c4={s->a[8],s->a[9]},c5={s->a[10],0};
    faithful_complex a=select_two(c0,c4,low&15,low>>4),b=select_two(c1,c5,low&15,low>>4),out;
    b=multiply(b,twiddle(low,0));c2=multiply(c2,twiddle(2*low,0));c3=multiply(c3,twiddle(3*low,0));
    unsigned which=bin>>6;
    if((which&1)==0){
        int64_t ar=add(a.r,c2.r),ai=add(a.i,c2.i),br=add(b.r,c3.r),bi=add(b.i,c3.i);
        out.r=which==0?add(ar,br):sub(ar,br);out.i=which==0?add(ai,bi):sub(ai,bi);
    }else{
        int64_t ar=sub(a.r,c2.r),ai=sub(a.i,c2.i),br=sub(b.r,c3.r),bi=sub(b.i,c3.i);
        out.r=which==1?add(ar,bi):sub(ar,bi);out.i=which==1?sub(ai,br):add(ai,br);
    }return out;
}
static int64_t half(int64_t value){uint64_t result=round_shift(magnitude(value),1);return value<0?-(int64_t)result:(int64_t)result;}
static compact_complex output(faithful_complex a,int exponent){compact_complex result={ldexpf((float)a.r,exponent),ldexpf((float)a.i,exponent)};return result;}
void codec2_analysis_forward(compact_transform *buffer,const float coefficients[11]){
    faithful_context state;float total=0;for(unsigned i=0;i<11;++i)total+=fabsf(coefficients[i]);
    int exponent;frexpf(total,&exponent);state.exponent=exponent-(CODEC2_FAITHFUL_BITS-3);
    for(unsigned i=0;i<11;++i){uint32_t bits;memcpy(&bits,&coefficients[i],4);state.a[i]=from_bits(bits,state.exponent);}
    faithful_complex dc=spectrum(&state,0),z={add(dc.r,dc.i),0},nq={sub(dc.r,dc.i),0};
    buffer->frequency[0]=output(z,state.exponent);buffer->frequency[256]=output(nq,state.exponent);
    for(unsigned k=1;k<=128;++k){
        faithful_complex a=spectrum(&state,k),b=spectrum(&state,256-k);b.i=-b.i;
        faithful_complex sum={add(a.r,b.r),add(a.i,b.i)},difference={sub(a.r,b.r),sub(a.i,b.i)},p=multiply(difference,twiddle(k-1,1));
        faithful_complex positive={half(add(sum.r,p.r)),half(add(sum.i,p.i))},negative={half(sub(sum.r,p.r)),half(sub(p.i,sum.i))};
        buffer->frequency[k]=output(positive,state.exponent);buffer->frequency[256-k]=output(negative,state.exponent);
    }
}
