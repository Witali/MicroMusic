/* Mode-4 uses the same LBR gain table, energy and arithmetic bounds as NB3.
 * Reuse the independently selectable C/ASM count-0..10 primitives at count8.
 * Xiph Speex 1.2.1 nb_celp/cb_search provenance: vendor COPYING (BSD). */
#ifndef MICROMUSIC_NB4_EXCITATION_H
#define MICROMUSIC_NB4_EXCITATION_H
#include "nb4_subframe.h"
#include "short_pitch.h"
static SPEEX_NB3_STAGE_O2 void speex_nb4_long_innovation(int16_t *out,const int16_t *in,const uint8_t *indices,int32_t scale,unsigned index)
{
    int8_t gain[3];
    for(unsigned i=0;i<3;i++)gain[i]=(int8_t)(32+AVR_READ_I8(gain_cdbk_lbr+index+2-i));
    for(unsigned vector=0;vector<5;vector++) {
        const int8_t *shape=exc_8_128_table+8*(unsigned)indices[vector];
#if SPEEX_NB3_USE_AVR_ASM
        speex_avr_long_innovation_n(out,in,shape,scale,gain,8);
#else
        speex_nb3_long_innovation10_c(out,in,shape,scale,gain,8);
#endif
        out+=8;in+=8;
    }
}
static SPEEX_NB3_STAGE void speex_nb4_zero_innovation(int16_t *out,const uint8_t *indices,int32_t scale)
{
    for(unsigned vector=0;vector<5;vector++) {
        const int8_t *shape=exc_8_128_table+8*(unsigned)indices[vector];
#if SPEEX_NB3_USE_AVR_ASM
        speex_avr_zero_innovation_n(out,shape,scale,8);
#else
        speex_nb3_zero_innovation_n_c(out,shape,scale,8);
#endif
        out+=8;
    }
}
static SPEEX_NB3_STAGE void speex_nb4_excitation_frame(int16_t *frame,const uint8_t *packet,int qe,uint8_t indices[5])
{
    for(uint8_t sub=0;sub<4;sub++) {
        int16_t *exc=frame+40*sub;
        uint16_t header=speex_nb4_unpack_subframe(packet,sub,indices);
        unsigned pitch=(header>>6)+17,index=((header>>1)&31)*4;
        int32_t energy=AVR_READ_I32(nb3_gain_table+(qe<<1)+(header&1));
        if(!index)speex_nb4_zero_innovation(exc,indices,energy);
        else if(pitch>=41)speex_nb4_long_innovation(exc,exc-pitch-1,indices,energy,index);
        else speex_nb4_short_innovation(exc,exc,(uint8_t)pitch,indices,energy,index);
    }
}
#endif
