/* Exact narrow sums and signed rounded averages, independent of ROM/CPU.
 * add/sub require a fitting int32 result. Rounded averages require a fitting
 * rounded result; sum's 33-bit numerator need not itself fit int32.
 */
#ifndef MICROMUSIC_CODEC2_WEIGHT_SUM32_H
#define MICROMUSIC_CODEC2_WEIGHT_SUM32_H
#include <assert.h>
#include <stdint.h>
#include <string.h>
#if defined(__GNUC__) || defined(__clang__)
#define SUM32_INLINE static inline __attribute__((always_inline))
#else
#define SUM32_INLINE static inline
#endif
SUM32_INLINE int32_t weight_add32(int32_t a,int32_t b){
#if CODEC2_WEIGHT_CHECKS
    int64_t wide=(int64_t)a+b;assert(wide>=INT32_MIN&&wide<=INT32_MAX);
#endif
    return a+b;
}
SUM32_INLINE int32_t weight_sub32(int32_t a,int32_t b){
#if CODEC2_WEIGHT_CHECKS
    int64_t wide=(int64_t)a-b;assert(wide>=INT32_MIN&&wide<=INT32_MAX);
#endif
    return a-b;
}
SUM32_INLINE int32_t weight_half32_bits(uint32_t word,uint32_t negative){
    uint32_t result=(word>>1)|(negative<<31);result+=(word&UINT32_C(1))&(negative^UINT32_C(1));
    int32_t out;memcpy(&out,&result,4);return out;
}
SUM32_INLINE int32_t weight_half_sum32(int32_t a,int32_t b){
    uint32_t ua=(uint32_t)a,ub=(uint32_t)b,word=ua+ub;
    uint32_t negative=((ua&ub)|((ua^ub)&word))>>31;
    return weight_half32_bits(word,negative);
}
SUM32_INLINE int32_t weight_half_difference32(int32_t a,int32_t b){
#if CODEC2_WEIGHT_CHECKS
    int64_t wide=(int64_t)a-b,half=wide<0?-((-wide+1)/2):(wide+1)/2;assert(half>=INT32_MIN&&half<=INT32_MAX);
#endif
    uint32_t ua=(uint32_t)a,ub=(uint32_t)b,word=ua-ub;
    uint32_t negative=((ua&~ub)|(~(ua^ub)&word))>>31;
    return weight_half32_bits(word,negative);
}
#undef SUM32_INLINE
#endif
