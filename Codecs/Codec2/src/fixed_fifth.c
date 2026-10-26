/* Original project implementation. No runtime float arithmetic, log or exp.
 * x = (1+m)*2^e, e = 5*q+r; interpolate (2^r*(1+m))^(1/5), r=0..4.
 * The generated table records its mathematical formula and integer formats.
 */
#include "fixed_fifth.h"
#include "fixed_table_access.h"
#include <float.h>
#include <stdint.h>
#include <string.h>
#ifndef CODEC2_ROOT_Q
#define CODEC2_ROOT_Q 11
#endif
#ifndef CODEC2_ROOT_TABLE_BITS
#define CODEC2_ROOT_TABLE_BITS 6
#endif
#if FLT_RADIX != 2 || FLT_MANT_DIG != 24
#error This boundary adapter requires IEEE binary32
#endif
typedef char binary32_size[(sizeof(float)==4)?1:-1];
#include <fixed_fifth_tables.inc>

static uint32_t node(unsigned index) {
#if CODEC2_ROOT_Q <= 15
    return CODEC2_TABLE_WORD(fifth_value, index);
#else
    unsigned offset=3*index;
    return (uint32_t)CODEC2_TABLE_BYTE(fifth_value,offset)
        | (uint32_t)CODEC2_TABLE_BYTE(fifth_value,offset+1)<<8
        | (uint32_t)CODEC2_TABLE_BYTE(fifth_value,offset+2)<<16;
#endif
}

float codec2_fixed_fifth(float value) {
    uint32_t bits; memcpy(&bits,&value,4);
    uint32_t magnitude=bits & UINT32_C(0x7fffffff);
    if (!magnitude) { bits=0; memcpy(&value,&bits,4); return value; }
    if (magnitude>UINT32_C(0x7f800000)) return value;
    if (bits & UINT32_C(0x80000000)) { bits=UINT32_C(0x7fc00000);memcpy(&value,&bits,4);return value; }
    if (magnitude==UINT32_C(0x7f800000)) return value;
    int exponent=(int)(bits>>23)-127;
    uint32_t mantissa=bits & UINT32_C(0x7fffff);
    if (exponent==-127) {
        exponent=-126;
        while (mantissa<UINT32_C(0x800000)) {mantissa<<=1;--exponent;}
        mantissa &= UINT32_C(0x7fffff);
    }
    /* u in [1,277]: floor(u/5) == (u*205)>>10. The product fits uint16. */
    uint16_t u=(uint16_t)(exponent+150);
    uint8_t quotient=(uint16_t)(u*UINT16_C(205))>>10;
    unsigned row=u-5*(unsigned)quotient;
    unsigned index=(unsigned)(mantissa>>(23-CODEC2_ROOT_TABLE_BITS));
    uint16_t fraction=(uint16_t)(mantissa>>(7-CODEC2_ROOT_TABLE_BITS));
    const unsigned count=1u<<CODEC2_ROOT_TABLE_BITS;
    unsigned at=row*(count+1)+index;
    uint32_t first=node(at), delta=node(at+1)-first;
    uint16_t complement=(uint16_t)(UINT16_C(0)-fraction);
    uint16_t tent=((uint32_t)fraction*complement+UINT32_C(32768))>>16;
    uint16_t curve=CODEC2_TABLE_WORD(fifth_curve,row*count+index);
    /* tent <= 65536-f; low slope and curve are each <=65535. Their sum
     * plus the rounding half-unit therefore fits uint32, without uint64.
     * One shared rounding also preserves monotonicity when delta>=curve.
     */
    uint32_t increment=((uint32_t)(uint16_t)delta*fraction+(uint32_t)curve*tent+UINT32_C(32768))>>16;
#if CODEC2_ROOT_Q-CODEC2_ROOT_TABLE_BITS > 16
    increment+=(delta>>16)*fraction;
#endif
    uint32_t result=((UINT32_C(1)<<CODEC2_ROOT_Q)+first+increment)<<(23-CODEC2_ROOT_Q);
    exponent=(int)quotient-30;
    if (result>=UINT32_C(0x1000000)) {result>>=1;++exponent;}
    bits=(uint32_t)(exponent+127)<<23 | (result & UINT32_C(0x7fffff));
    memcpy(&value,&bits,4); return value;
}
