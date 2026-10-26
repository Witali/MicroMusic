/* Exact symmetric rounding of an int64 product to an int32 result, 1<=q<=30.
 * Contract: the rounded result fits int32. No negative signed shifts or ASM.
 */
#ifndef MICROMUSIC_CODEC2_WEIGHT_ROUND_H
#define MICROMUSIC_CODEC2_WEIGHT_ROUND_H
#include <stdint.h>
#include <string.h>
#if defined(__GNUC__) || defined(__clang__)
static inline __attribute__((always_inline)) int32_t weight_round64(int64_t value,unsigned q){
#else
static inline int32_t weight_round64(int64_t value,unsigned q){
#endif
    uint32_t low=(uint32_t)(uint64_t)value,high=(uint32_t)((uint64_t)value>>32);
    uint32_t previous=low,bias=(UINT32_C(1)<<(q-1))-(high>>31);
    low+=bias;high+=(low<previous);
    uint32_t bits=(low>>q)|(high<<(32-q));int32_t result;memcpy(&result,&bits,4);return result;
}
#endif
