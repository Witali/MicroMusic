/* Coefficients and arithmetic derived from Xiph Speex 1.2.1 sb_celp.c and
 * filters.c, Copyright (C) 2002-2006 Jean-Marc Valin. BSD license retained in
 * vendor/speex-1.2.1/COPYING. Input permutation/history layout are local. */
#include "qmf_memory.h"
#ifdef __AVR__
#include <avr/pgmspace.h>
#define FLASH PROGMEM
#define COEF(i) ((int16_t)pgm_read_word(coefficients+(i)))
#else
#define FLASH
#define COEF(i) coefficients[i]
#endif
static const int16_t coefficients[64] FLASH = {
 2,-7,-7,18,15,-39,-25,75,35,-130,-41,212,38,-327,-17,483,
 -32,-689,124,956,-283,-1307,543,1780,-973,-2467,1733,3633,-3339,-6409,9059,30153,
 30153,9059,-6409,-3339,3633,1733,-2467,-973,1780,543,-1307,-283,956,124,-689,-32,
 483,-17,-327,38,212,-41,-130,35,75,-25,-39,15,18,-7,-7,2};

static uint16_t successor(uint16_t i, uint16_t modulus)
{
    i *= 2;
    return i >= modulus ? i-modulus : i;
}

static int16_t rounded_pcm(uint32_t accumulator)
{
    /* Unsigned addition defines upstream's modulo-32 accumulation/rounding. */
    int32_t value = (int32_t)(accumulator + 16384u) >> 15;
    if (value > 32767) value = 32767;
    if (value < -32767) value = -32767;
    return (int16_t)value;
}

static inline uint32_t multiply17(int16_t coefficient, int32_t value)
{
    /* The low/high sum or difference needs 17 bits. Multiplying its wrapped
     * s16 part and restoring the carry saves two products per QMF tap pair.
     * Do not add/subtract the inputs in s16 without this correction. */
    uint32_t result=(uint32_t)((int32_t)coefficient*(int16_t)value);
    if (value>32767) result += (uint32_t)(int32_t)coefficient << 16;
    else if (value < -32768) result -= (uint32_t)(int32_t)coefficient << 16;
    return result;
}

void speex_avr_qmf_memory(int16_t *pcm, uint16_t n,
                          int16_t *low_history, int16_t *high_history)
{
    uint16_t start, half=n/2, modulus=n-1;
    /* Perfect shuffle in place. A cycle is processed only from its smallest
     * member. No visited bitmap and no frame-sized temporary are needed. */
    for (start=1; start<modulus; ++start) {
        uint16_t next=successor(start,modulus), current;
        int16_t carry;
        while (next>start) next=successor(next,modulus);
        if (next!=start) continue;
        carry=pcm[start]; current=start;
        do {
            int16_t saved;
            next=successor(current,modulus);
            saved=pcm[next]; pcm[next]=carry; carry=saved; current=next;
        } while (current!=start);
    }
    for (start=0; start<half; ++start) {
        uint8_t k, index=(uint8_t)start & 31;
        uint32_t even=0, odd=0;
        low_history[index]=pcm[2*start];
        high_history[index]=pcm[2*start+1];
        for (k=0; k<32; ++k) {
            int16_t low=low_history[index], high=high_history[index];
            int16_t a=COEF(2*k), b=COEF(2*k+1);
            even += multiply17(a,(int32_t)low-high);
            odd += multiply17(b,(int32_t)low+high);
            index=(index-1)&31;
        }
        pcm[2*start]=rounded_pcm(even);
        pcm[2*start+1]=rounded_pcm(odd);
    }
}
