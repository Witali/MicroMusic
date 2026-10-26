/* Project fixed-point adaptation of pinned KISS sparse radix-four/real FFT.
 * Complete original KISS BSD conditions accompany fixed_weight_tables.inc.
 * Finite gamma-weighted mode-3200 LPC inputs; portable C arithmetic only.
 */
#include "fixed_weight.h"
#include "spectral_table_access.h"
#include <assert.h>
#include <math.h>
#include <string.h>
#ifndef CODEC2_WEIGHT_BITS
#define CODEC2_WEIGHT_BITS 32
#endif
#ifndef CODEC2_WEIGHT_TWIDDLE_Q
#define CODEC2_WEIGHT_TWIDDLE_Q 30
#endif
#ifndef CODEC2_WEIGHT_CHECKS
#define CODEC2_WEIGHT_CHECKS 0
#endif
#if CODEC2_WEIGHT_BITS !=16 && CODEC2_WEIGHT_BITS !=24 && CODEC2_WEIGHT_BITS !=32
#error Unsupported weighted spectrum precision
#endif
#if CODEC2_WEIGHT_TWIDDLE_Q !=14 && CODEC2_WEIGHT_TWIDDLE_Q !=22 && CODEC2_WEIGHT_TWIDDLE_Q !=30
#error Unsupported weighted spectrum twiddle precision
#endif
#include "fixed_weight_tables.inc"
typedef struct {int32_t r,i;} complex_fixed;

static int32_t checked(int64_t value){
#if CODEC2_WEIGHT_CHECKS
    assert(value>=-(INT64_C(1)<<(CODEC2_WEIGHT_BITS-1))&&value<(INT64_C(1)<<(CODEC2_WEIGHT_BITS-1)));
#endif
    return (int32_t)value;
}
static int64_t rounded(int64_t value,unsigned bits){
    int64_t half=INT64_C(1)<<(bits-1);
    return value<0?-((-value+half)>>bits):(value+half)>>bits;
}
static complex_fixed twiddle(unsigned index,int super){
    complex_fixed value;
#if CODEC2_WEIGHT_TWIDDLE_Q ==14
    value.r=(int16_t)(super?CODEC2_TABLE_WORD(weight_super,2*index):CODEC2_TABLE_WORD(weight_twiddle,2*index));
    value.i=(int16_t)(super?CODEC2_TABLE_WORD(weight_super,2*index+1):CODEC2_TABLE_WORD(weight_twiddle,2*index+1));
#else
    uint32_t r=super?CODEC2_TABLE_DWORD(weight_super,2*index):CODEC2_TABLE_DWORD(weight_twiddle,2*index);
    uint32_t i=super?CODEC2_TABLE_DWORD(weight_super,2*index+1):CODEC2_TABLE_DWORD(weight_twiddle,2*index+1);
    memcpy(&value.r,&r,4);memcpy(&value.i,&i,4);
#endif
    return value;
}
static complex_fixed multiply(complex_fixed a,complex_fixed b){
    complex_fixed result={checked(rounded((int64_t)a.r*b.r-(int64_t)a.i*b.i,CODEC2_WEIGHT_TWIDDLE_Q)),
                          checked(rounded((int64_t)a.r*b.i+(int64_t)a.i*b.r,CODEC2_WEIGHT_TWIDDLE_Q))};
    return result;
}
static complex_fixed select_two(complex_fixed a,complex_fixed b,unsigned j,unsigned which){
    complex_fixed p=multiply(b,twiddle(4*j,0)),out;
    if(which==0){out.r=checked((int64_t)a.r+p.r);out.i=checked((int64_t)a.i+p.i);}
    else if(which==2){out.r=checked((int64_t)a.r-p.r);out.i=checked((int64_t)a.i-p.i);}
    else if(which==1){out.r=checked((int64_t)a.r+p.i);out.i=checked((int64_t)a.i-p.r);}
    else {out.r=checked((int64_t)a.r-p.i);out.i=checked((int64_t)a.i+p.r);}
    return out;
}
static complex_fixed spectrum(const codec2_weight *s,unsigned bin){
    complex_fixed c[6];for(unsigned i=0;i<6;++i){c[i].r=s->coefficient[2*i];c[i].i=i<5?s->coefficient[2*i+1]:0;}
    unsigned low=bin&63;
    complex_fixed a=select_two(c[0],c[4],low&15,low>>4);
    complex_fixed b=select_two(c[1],c[5],low&15,low>>4);
    b=multiply(b,twiddle(low,0));c[2]=multiply(c[2],twiddle(2*low,0));c[3]=multiply(c[3],twiddle(3*low,0));
    unsigned which=bin>>6;complex_fixed out;
    if((which&1)==0){
        int64_t ar=(int64_t)a.r+c[2].r,ai=(int64_t)a.i+c[2].i,br=(int64_t)b.r+c[3].r,bi=(int64_t)b.i+c[3].i;
        out.r=checked(which==0?ar+br:ar-br);out.i=checked(which==0?ai+bi:ai-bi);
    }else{
        int64_t ar=(int64_t)a.r-c[2].r,ai=(int64_t)a.i-c[2].i,br=(int64_t)b.r-c[3].r,bi=(int64_t)b.i-c[3].i;
        out.r=checked(which==1?ar+bi:ar-bi);out.i=checked(which==1?ai-br:ai+br);
    }
    return out;
}
void codec2_weight_init(codec2_weight *s,const float coefficient[11]){
    float total=0;for(unsigned i=0;i<11;++i)total+=fabsf(coefficient[i]);
    int exponent;frexpf(total,&exponent);s->exponent=exponent-(CODEC2_WEIGHT_BITS-3);
    for(unsigned i=0;i<11;++i){float value=ldexpf(coefficient[i],-s->exponent);s->coefficient[i]=checked((int64_t)(value<0?value-.5f:value+.5f));}
}
compact_complex codec2_weight_dc(const codec2_weight *s){
    complex_fixed dc=spectrum(s,0);compact_complex out={ldexpf((float)checked((int64_t)dc.r+dc.i),s->exponent),0};return out;
}
void codec2_weight_pair(const codec2_weight *s,unsigned k,compact_complex *positive,compact_complex *negative){
    complex_fixed a=spectrum(s,k),b=spectrum(s,256-k);b.i=-b.i;
    complex_fixed sum={checked((int64_t)a.r+b.r),checked((int64_t)a.i+b.i)};
    complex_fixed difference={checked((int64_t)a.r-b.r),checked((int64_t)a.i-b.i)};
    complex_fixed p=multiply(difference,twiddle(k-1,1));
    int32_t pr=checked(rounded((int64_t)sum.r+p.r,1)),pi=checked(rounded((int64_t)sum.i+p.i,1));
    int32_t nr=checked(rounded((int64_t)sum.r-p.r,1)),ni=checked(rounded((int64_t)p.i-sum.i,1));
    positive->r=ldexpf((float)pr,s->exponent);positive->i=ldexpf((float)pi,s->exponent);
    negative->r=ldexpf((float)nr,s->exponent);negative->i=ldexpf((float)ni,s->exponent);
}
