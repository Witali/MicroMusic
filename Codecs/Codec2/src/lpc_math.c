/* Portable integer cosine/angle boundaries; Q60 Taylor evaluation and exact
 * binary32 packing. No floating arithmetic inside cosine or grid conversion.
 */
#include "lpc_math.h"
#include "table_access.h"
#include <assert.h>
#include <float.h>
#include <string.h>
#ifndef CODEC2_LPC_MATH_CHECKS
#define CODEC2_LPC_MATH_CHECKS 0
#endif
#if FLT_RADIX != 2 || FLT_MANT_DIG != 24
#error IEEE binary32 is required at this boundary
#endif
typedef char lpc_math_binary32_size[(sizeof(float)==4)?1:-1];
#include "lpc_math_tables.inc"
#ifndef CODEC2_LPC_NATIVE_COMPAT
#define CODEC2_LPC_NATIVE_COMPAT 0
#endif
#if CODEC2_LPC_NATIVE_COMPAT
#include "lpc_math_compat.inc"
static uint32_t compat_word(unsigned index){
#if defined(__AVR__)
    return pgm_read_dword(&lpc_cosine_compat[index]);
#else
    return lpc_cosine_compat[index];
#endif
}
#endif
static int64_t coefficient(unsigned index){
#if defined(__AVR__)
    uint64_t bits=pgm_read_dword((const uint8_t *)&lpc_sine_coefficient[index]);
    bits|=(uint64_t)pgm_read_dword((const uint8_t *)&lpc_sine_coefficient[index]+4)<<32;
    int64_t result;memcpy(&result,&bits,8);return result;
#else
    return lpc_sine_coefficient[index];
#endif
}
static uint64_t magnitude(int64_t x){return x<0?UINT64_C(0)-(uint64_t)x:(uint64_t)x;}
static unsigned bit_length(uint64_t x){
    uint32_t hi=(uint32_t)(x>>32),word=hi?hi:(uint32_t)x;unsigned n=hi?32:0;
    if(word>>16){word>>=16;n+=16;}if(word>>8){word>>=8;n+=8;}if(word>>4){word>>=4;n+=4;}
    if(word>>2){word>>=2;n+=2;}if(word>>1){word>>=1;++n;}return n+(word!=0);
}
static uint64_t rounded(uint64_t x,unsigned shift){
    if(!shift)return x;uint64_t out=x>>shift,tail=x&((UINT64_C(1)<<shift)-1),half=UINT64_C(1)<<(shift-1);
    return out+(tail>half||(tail==half&&(out&1)));
}
static float pack(int64_t x,unsigned q){
    uint64_t a=magnitude(x);unsigned width=bit_length(a);uint32_t bits=0;
    if(width){
        uint64_t mantissa=width>24?rounded(a,width-24):a<<(24-width);int exponent=(int)width-1-(int)q;
        if(mantissa==UINT64_C(0x1000000)){mantissa>>=1;++exponent;}
        bits=((uint32_t)(exponent+127)<<23)|((uint32_t)mantissa&UINT32_C(0x7fffff));
        if(x<0)bits|=UINT32_C(0x80000000);
    }
    float result;memcpy(&result,&bits,4);return result;
}
static int64_t mul_q60(int64_t a,int64_t b){
    uint64_t ua=magnitude(a),ub=magnitude(b);uint32_t al=(uint32_t)ua,ah=(uint32_t)(ua>>32),bl=(uint32_t)ub,bh=(uint32_t)(ub>>32);
    uint64_t low=(uint64_t)al*bl,high=(uint64_t)ah*bh,cross=(uint64_t)ah*bl,previous=low;
    low+=cross<<32;high+=(cross>>32)+(low<previous);cross=(uint64_t)al*bh;previous=low;
    low+=cross<<32;high+=(cross>>32)+(low<previous);
    uint64_t value=(high<<4)|(low>>60),tail=low&((UINT64_C(1)<<60)-1),half=UINT64_C(1)<<59;
    value+=tail>half||(tail==half&&(value&1));return (a<0)!=(b<0)?-(int64_t)value:(int64_t)value;
}
static float mathematical_cosine(float angle){
    uint32_t bits;memcpy(&bits,&angle,4);bits&=UINT32_C(0x7fffffff);
#if CODEC2_LPC_MATH_CHECKS
    assert(bits<UINT32_C(0x41000000));
#endif
    unsigned field=bits>>23;if(field<100)return 1.0f; /* cosine rounds to one */
    uint32_t mantissa=(bits&UINT32_C(0x7fffff))|UINT32_C(0x800000);int shift=(int)field-150+60;
    int64_t phase=shift>=0?(int64_t)((uint64_t)mantissa<<shift):(int64_t)rounded(mantissa,(unsigned)-shift);
    if(phase>LPC_PI_Q60)phase-=LPC_TWO_PI_Q60;if(phase<0)phase=-phase;
    int64_t x=LPC_HALF_PI_Q60-phase,z=mul_q60(x,x),p=coefficient(9);
    for(unsigned i=9;i>0;--i)p=coefficient(i-1)+mul_q60(p,z);
    return pack(mul_q60(x,p),60);
}
float codec2_lpc_cosf(float angle){
#if CODEC2_LPC_NATIVE_COMPAT
    uint32_t key;memcpy(&key,&angle,4);key&=UINT32_C(0x7fffffff);
    unsigned low=0,high=LPC_COSINE_COMPAT_COUNT;
    while(low<high){unsigned mid=low+(high-low)/2;uint32_t candidate=compat_word(2*mid);
        if(candidate<key)low=mid+1;else high=mid;}
    if(low<LPC_COSINE_COMPAT_COUNT&&compat_word(2*low)==key){uint32_t bits=compat_word(2*low+1);float value;memcpy(&value,&bits,4);return value;}
#endif
    return mathematical_cosine(angle);
}
float codec2_lpc_grid_angle(uint16_t grid){
#if CODEC2_LPC_MATH_CHECKS
    assert(grid<=392);
#endif
    return pack((int64_t)((uint64_t)grid*LPC_GRID_Q54),54);
}
float codec2_lpc_initial_angle(unsigned index){
#if CODEC2_LPC_MATH_CHECKS
    assert(index<10);
#endif
#if defined(__AVR__)
    uint32_t bits=pgm_read_dword(&lpc_initial_bits[index]);
#else
    uint32_t bits=lpc_initial_bits[index];
#endif
    float result;memcpy(&result,&bits,4);return result;
}
