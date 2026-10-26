/* Exact signed 24x24 multiplication and complex rounding without int64.
 * Pure C optimization, independently selectable from storage/hardware access.
 * Operands must be within signed24; complex sums fit signed48 for this profile.
 */
#ifndef MICROMUSIC_CODEC2_WEIGHT_MUL24_H
#define MICROMUSIC_CODEC2_WEIGHT_MUL24_H
#include <stdint.h>
#if defined(__GNUC__) || defined(__clang__)
#define WEIGHT_INLINE static inline __attribute__((always_inline))
#else
#define WEIGHT_INLINE static inline
#endif
typedef struct { uint32_t low; uint16_t high; } weight_wide48;
WEIGHT_INLINE weight_wide48 weight_neg48(weight_wide48 a){
    a.low=UINT32_C(0)-a.low;a.high=(uint16_t)(~a.high+(a.low==0));return a;
}
WEIGHT_INLINE weight_wide48 weight_product24(int32_t a,int32_t b){
    uint32_t ua=a<0?UINT32_C(0)-(uint32_t)a:(uint32_t)a;
    uint32_t ub=b<0?UINT32_C(0)-(uint32_t)b:(uint32_t)b;
    uint16_t al=(uint16_t)ua,bl=(uint16_t)ub;uint8_t ah=(uint8_t)(ua>>16),bh=(uint8_t)(ub>>16);
    uint32_t low=(uint32_t)al*bl,cross=(uint32_t)ah*bl+(uint32_t)bh*al;
    weight_wide48 result;result.low=low+(cross<<16);
    result.high=(uint16_t)((uint16_t)ah*bh+(cross>>16)+(result.low<low));
    return (a<0)!=(b<0)?weight_neg48(result):result;
}
WEIGHT_INLINE weight_wide48 weight_add48(weight_wide48 a,weight_wide48 b){
    weight_wide48 out;out.low=a.low+b.low;out.high=(uint16_t)(a.high+b.high+(out.low<a.low));return out;
}
WEIGHT_INLINE weight_wide48 weight_sub48(weight_wide48 a,weight_wide48 b){
    weight_wide48 out;out.low=a.low-b.low;out.high=(uint16_t)(a.high-b.high-(a.low<b.low));return out;
}
WEIGHT_INLINE int32_t weight_round48(weight_wide48 a,unsigned bits){
    uint8_t negative=(a.high&0x8000)!=0;if(negative)a=weight_neg48(a);
    uint32_t previous=a.low;a.low+=UINT32_C(1)<<(bits-1);a.high+=(a.low<previous);
    uint32_t result=(a.low>>bits)|((uint32_t)a.high<<(32-bits));
    return negative?-(int32_t)result:(int32_t)result;
}
#undef WEIGHT_INLINE
#endif
