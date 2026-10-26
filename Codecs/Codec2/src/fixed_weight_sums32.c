/* Generated exact narrow sums for the paired C graph; original wide C remains selectable. */
/* Project fixed-point adaptation of pinned KISS sparse radix-four/real FFT.
 * Complete original KISS BSD conditions accompany fixed_weight_tables.inc.
 * Finite gamma-weighted mode-3200 LPC inputs; portable C arithmetic only.
 */
#include "fixed_weight.h"
#include "spectral_table_access.h"
#include <assert.h>
#include <math.h>
#include <string.h>
#ifndef CODEC2_WEIGHT_SPLIT24
#define CODEC2_WEIGHT_SPLIT24 0
#endif
#ifndef CODEC2_WEIGHT_CHECKS
#define CODEC2_WEIGHT_CHECKS 0
#endif
#ifndef CODEC2_WEIGHT_DIRECT_PAIR
#define CODEC2_WEIGHT_DIRECT_PAIR 0
#endif
#ifndef CODEC2_WEIGHT_ROUND_LEGACY
#define CODEC2_WEIGHT_ROUND_LEGACY 0
#endif
#if CODEC2_WEIGHT_BITS !=16 && CODEC2_WEIGHT_BITS !=24 && CODEC2_WEIGHT_BITS !=32
#error Unsupported weighted spectrum precision
#endif
#if CODEC2_WEIGHT_TWIDDLE_Q !=14 && CODEC2_WEIGHT_TWIDDLE_Q !=22 && CODEC2_WEIGHT_TWIDDLE_Q !=30
#error Unsupported weighted spectrum twiddle precision
#endif
#include "fixed_weight_tables.inc"
#if CODEC2_WEIGHT_SPLIT24
#if CODEC2_WEIGHT_BITS > 24 || CODEC2_WEIGHT_TWIDDLE_Q > 22
#error Split24 multiplication requires operands bounded to signed24
#endif
#include "weight_mul24.h"
#endif
typedef struct {codec2_weight_component r,i;} complex_fixed;
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


static codec2_weight_component checked(int64_t value){
#if CODEC2_WEIGHT_CHECKS
    assert(value>=-(INT64_C(1)<<(CODEC2_WEIGHT_BITS-1))&&value<(INT64_C(1)<<(CODEC2_WEIGHT_BITS-1)));
#endif
    return (codec2_weight_component)value;
}
#if CODEC2_WEIGHT_ROUND_LEGACY
static int64_t rounded(int64_t value,unsigned bits){
    int64_t half=INT64_C(1)<<(bits-1);
    return value<0?-((-value+half)>>bits):(value+half)>>bits;
}
#else
#include "weight_round.h"
#define rounded weight_round64
#endif
static complex_fixed twiddle(unsigned index,int super){
    complex_fixed value;
#if CODEC2_WEIGHT_TWIDDLE_Q ==14
    value.r=(int16_t)(super?CODEC2_TABLE_WORD(weight_super,2*index):CODEC2_TABLE_WORD(weight_twiddle,2*index));
    value.i=(int16_t)(super?CODEC2_TABLE_WORD(weight_super,2*index+1):CODEC2_TABLE_WORD(weight_twiddle,2*index+1));
#else
    uint32_t r=super?CODEC2_TABLE_DWORD(weight_super,2*index):CODEC2_TABLE_DWORD(weight_twiddle,2*index);
    uint32_t i=super?CODEC2_TABLE_DWORD(weight_super,2*index+1):CODEC2_TABLE_DWORD(weight_twiddle,2*index+1);
    int32_t sr,si;memcpy(&sr,&r,4);memcpy(&si,&i,4);value.r=sr;value.i=si;
#endif
    return value;
}
static complex_fixed multiply(complex_fixed a,complex_fixed b){
#if CODEC2_WEIGHT_SPLIT24
    complex_fixed result;
    result.r=checked(weight_round48(weight_sub48(weight_product24(a.r,b.r),weight_product24(a.i,b.i)),CODEC2_WEIGHT_TWIDDLE_Q));
    result.i=checked(weight_round48(weight_add48(weight_product24(a.r,b.i),weight_product24(a.i,b.r)),CODEC2_WEIGHT_TWIDDLE_Q));
#else
    complex_fixed result={checked32(rounded((int64_t)a.r*b.r-(int64_t)a.i*b.i,CODEC2_WEIGHT_TWIDDLE_Q)),
                          checked32(rounded((int64_t)a.r*b.i+(int64_t)a.i*b.r,CODEC2_WEIGHT_TWIDDLE_Q))};
#endif
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
    for(unsigned i=0;i<11;++i){float value=ldexpf(coefficient[i],-s->exponent);s->coefficient[i]=checked32((int32_t)(value<0?value-.5f:value+.5f));}
}
compact_complex codec2_weight_dc(const codec2_weight *s){
#if CODEC2_WEIGHT_DIRECT_PAIR
    int32_t sum=0;for(unsigned i=0;i<11;++i)sum=weight_add32(sum,s->coefficient[i]);compact_complex out={ldexpf((float)checked32(sum),s->exponent),0};return out;
#else
    complex_fixed dc=spectrum(s,0);compact_complex out={ldexpf((float)checked((int64_t)dc.r+dc.i),s->exponent),0};return out;
#endif
}
void codec2_weight_pair(const codec2_weight *s,unsigned k,compact_complex *positive,compact_complex *negative){
#if CODEC2_WEIGHT_DIRECT_PAIR
    /* Z(k)=sum(c[n]*W^(n*k)), six packed complex inputs. Compute Z(-k)
     * with conjugate coefficients in the same pass, sharing all four real
     * products per term. This is a new rounding graph, independently gated.
     */
    complex_fixed a={s->coefficient[0],s->coefficient[1]},b=a;
    for(unsigned n=1;n<5;++n){
        complex_fixed w=twiddle((n*k)&255,0);
        int32_t r=s->coefficient[2*n],i=s->coefficient[2*n+1];
#if CODEC2_WEIGHT_SPLIT24
        weight_wide48 rr=weight_product24(r,w.r),ii=weight_product24(i,w.i);
        a.r=checked((int64_t)a.r+weight_round48(weight_sub48(rr,ii),CODEC2_WEIGHT_TWIDDLE_Q));
        b.r=checked((int64_t)b.r+weight_round48(weight_add48(rr,ii),CODEC2_WEIGHT_TWIDDLE_Q));
        weight_wide48 ri=weight_product24(r,w.i),ir=weight_product24(i,w.r);
        a.i=checked((int64_t)a.i+weight_round48(weight_add48(ri,ir),CODEC2_WEIGHT_TWIDDLE_Q));
        b.i=checked((int64_t)b.i+weight_round48(weight_sub48(ir,ri),CODEC2_WEIGHT_TWIDDLE_Q));
#else
        int64_t rr=(int64_t)r*w.r,ii=(int64_t)i*w.i;
        a.r=checked32(weight_add32(a.r,rounded(rr-ii,CODEC2_WEIGHT_TWIDDLE_Q)));
        b.r=checked32(weight_add32(b.r,rounded(rr+ii,CODEC2_WEIGHT_TWIDDLE_Q)));
        int64_t ri=(int64_t)r*w.i,ir=(int64_t)i*w.r;
        a.i=checked32(weight_add32(a.i,rounded(ri+ir,CODEC2_WEIGHT_TWIDDLE_Q)));
        b.i=checked32(weight_add32(b.i,rounded(ir-ri,CODEC2_WEIGHT_TWIDDLE_Q)));
#endif
    }
    /* Last packed input is real-only: its conjugate pair shares both rounded
     * products exactly, avoiding zero products and duplicate rounding. */
    complex_fixed last=twiddle((5*k)&255,0);int32_t real=s->coefficient[10],lr,li;
#if CODEC2_WEIGHT_SPLIT24
    lr=weight_round48(weight_product24(real,last.r),CODEC2_WEIGHT_TWIDDLE_Q);
    li=weight_round48(weight_product24(real,last.i),CODEC2_WEIGHT_TWIDDLE_Q);
#else
    lr=rounded((int64_t)real*last.r,CODEC2_WEIGHT_TWIDDLE_Q);
    li=rounded((int64_t)real*last.i,CODEC2_WEIGHT_TWIDDLE_Q);
#endif
    a.r=checked32(weight_add32(a.r,lr));b.r=checked32(weight_add32(b.r,lr));
    a.i=checked32(weight_add32(a.i,li));b.i=checked32(weight_sub32(b.i,li));
#else
    complex_fixed a=spectrum(s,k),b=spectrum(s,256-k);b.i=-b.i;
#endif
#if CODEC2_WEIGHT_DIRECT_PAIR
    b.i=-b.i;
#endif
    complex_fixed sum={checked32(weight_add32(a.r,b.r)),checked32(weight_add32(a.i,b.i))};
    complex_fixed difference={checked32(weight_sub32(a.r,b.r)),checked32(weight_sub32(a.i,b.i))};
    complex_fixed p=multiply(difference,twiddle(k-1,1));
    int32_t pr=checked32(weight_half_sum32(sum.r,p.r)),pi=checked32(weight_half_sum32(sum.i,p.i));
    int32_t nr=checked32(weight_half_difference32(sum.r,p.r)),ni=checked32(weight_half_difference32(p.i,sum.i));
    positive->r=ldexpf((float)pr,s->exponent);positive->i=ldexpf((float)pi,s->exponent);
    negative->r=ldexpf((float)nr,s->exponent);negative->i=ldexpf((float)ni,s->exponent);
}
