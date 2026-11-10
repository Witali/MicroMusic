#include "nb3_indices.h"
/* Exact short-pitch excitation for Xiph NB3/NB4, pitch 17..40.
 * Choose contiguous history ranges before each inner loop. Four isolated
 * switch/tail samples keep the original three-tap source indices. Every
 * history read is completed before output is written. Xiph BSD provenance:
 * Copyright (C) 2002-2006 Jean-Marc Valin; vendor/speex-1.2.1/COPYING. */
#ifndef MICROMUSIC_NB3_SHORT_PITCH_H
#define MICROMUSIC_NB3_SHORT_PITCH_H
#include "speex/speex_bits.h"
#include "long_pitch.h"
#include "zero_innovation.h"
extern const signed char gain_cdbk_lbr[],exc_10_32_table[],exc_8_128_table[];
#if !SPEEX_NB3_USE_AVR_ASM
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_nb3_segment_finish_c(int32_t adaptive,
    int8_t shape,int16_t high,int16_t low)
{
    int32_t innovation=speex_nb3_shape_scale_c(shape,high,low);
    if(adaptive>2048000) adaptive=2048000;
    if(adaptive<-2048000) adaptive=-2048000;
    return speex_nb3_saturating_q14_c(
        (int32_t)(((uint32_t)adaptive<<8)+(uint32_t)innovation+8192));
}
#endif
#if SPEEX_NB3_USE_AVR_ASM && SPEEX_ENABLE_NB4
/* Two geometries share one controller on the explicitly enabled ASM backend. */
static SPEEX_NB3_STAGE void speex_short_innovation_shared(int16_t *out,const int16_t *exc,uint8_t pitch,
    const uint8_t *input_indices,int32_t scale,unsigned index,const int8_t *table,uint8_t geometry)
{
    const uint8_t vectors=geometry&7,width=geometry>>3;
    const uint8_t *indices=input_indices;
    int8_t gains[3];
    int16_t edge[3];
    const uint8_t first=pitch-1,second=2*pitch-1;
    uint8_t vector,j=0;
    gains[0]=(int8_t)(32+AVR_READ_I8(gain_cdbk_lbr+index+2));
    gains[1]=(int8_t)(32+AVR_READ_I8(gain_cdbk_lbr+index+1));
    gains[2]=(int8_t)(32+AVR_READ_I8(gain_cdbk_lbr+index));
    for(vector=0;vector<vectors;vector++) {
        unsigned code=indices[vector];
        const int8_t *shape=table+width*code;
        uint8_t left=width;
        while(left) {
            const int16_t *in;
            uint8_t count;
            if(j<first) {
                in=exc+(int)j-pitch-1;count=first-j;
            } else if(j>pitch && j<second) {
                in=exc+(int)j-2*pitch-1;count=second-j;
            } else {
                if(j==first) {
                    edge[0]=exc[-2];edge[1]=exc[-1];edge[2]=exc[-pitch];
                    in=edge;count=1;
                } else if(j==pitch) {
                    edge[0]=exc[-1];edge[1]=exc[-pitch];edge[2]=exc[1-pitch];
                    in=edge;count=1;
                } else if(j==second) {
                    edge[0]=exc[-2];edge[1]=exc[-1];edge[2]=0;
                    in=edge;count=1;
                } else if(j==second+1) {
                    edge[0]=exc[-1];edge[1]=0;edge[2]=0;
                    in=edge;count=1;
                } else {
                    /* The original tap rule has no remaining history. */
                    speex_avr_zero_innovation_n(out,shape,scale,left);
                    out+=left;shape+=left;j+=left;
                    break;
                }
            }
            if(count>left) count=left;
            if (count==1)
                speex_avr_long_innovation1(out,in,shape,scale,gains);
            else
                speex_avr_long_innovation_n(out,in,shape,scale,gains,count);
            out+=count;shape+=count;j+=count;left-=count;
        }
    }
}

static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_short_innovation(int16_t *out,const int16_t *exc,uint8_t pitch,
    const uint8_t *indices,int32_t scale,unsigned index
#if SPEEX_ENABLE_NB2
    ,const int8_t *table
#endif
)
{
#if !SPEEX_ENABLE_NB2
    const int8_t *table=exc_10_32_table;
#endif
    speex_short_innovation_shared(out,exc,pitch,indices,scale,index,table,84);
}
static SPEEX_NB3_ALWAYS_INLINE void speex_nb4_short_innovation(int16_t *out,const int16_t *exc,uint8_t pitch,
    const uint8_t *indices,int32_t scale,unsigned index)
{speex_short_innovation_shared(out,exc,pitch,indices,scale,index,exc_8_128_table,69);}
#else
#define SPEEX_SHORT_NAME speex_nb3_short_innovation
#define SPEEX_SHORT_VECTORS 4
#define SPEEX_SHORT_SIZE 10
#if SPEEX_ENABLE_NB2
#define SPEEX_SHORT_DYNAMIC_TABLE 1
#define SPEEX_SHORT_TABLE table
#else
#define SPEEX_SHORT_TABLE exc_10_32_table
#endif
#include "short_pitch_kernel.inc"
#undef SPEEX_SHORT_NAME
#undef SPEEX_SHORT_VECTORS
#undef SPEEX_SHORT_SIZE
#undef SPEEX_SHORT_TABLE
#ifdef SPEEX_SHORT_DYNAMIC_TABLE
#undef SPEEX_SHORT_DYNAMIC_TABLE
#endif
#if SPEEX_ENABLE_NB4
#define SPEEX_SHORT_NAME speex_nb4_short_innovation
#define SPEEX_SHORT_VECTORS 5
#define SPEEX_SHORT_SIZE 8
#define SPEEX_SHORT_TABLE exc_8_128_table
#include "short_pitch_kernel.inc"
#undef SPEEX_SHORT_NAME
#undef SPEEX_SHORT_VECTORS
#undef SPEEX_SHORT_SIZE
#undef SPEEX_SHORT_TABLE
#endif
#endif /* shared-controller selection */
#endif
