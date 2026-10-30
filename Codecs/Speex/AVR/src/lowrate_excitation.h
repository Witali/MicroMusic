/* Low-rate frame/controller differences; synthesis stays shared.
 * Adapted from Xiph Speex 1.2.1 nb_celp.c / modes.c (vendor COPYING, BSD).
 * The optional NB2 table shares the existing signed8 LBR pitch gains and
 * 4x10-sample geometry; arithmetic backend selection is unchanged. */
#ifndef MICROMUSIC_SPEEX_LOWRATE_EXCITATION_H
#define MICROMUSIC_SPEEX_LOWRATE_EXCITATION_H
#include "packet_mode.h"
#include "short_pitch.h"
extern const int8_t exc_10_16_table[160];
static SPEEX_NB3_NOINLINE void speex_low_unpack(const uint8_t *packet,uint8_t sub,uint8_t indices[4])
{
    unsigned at=40+21*(unsigned)sub;
    for(uint8_t v=0;v<4;v++,at+=4)indices[v]=speex_packet_field(packet,at,4);
}
#if SPEEX_ENABLE_NB2
static SPEEX_NB3_STAGE_O2 void speex_nb2_excitation_frame(int16_t *frame,
    const uint8_t *packet,int32_t scale,uint8_t indices[4])
{
    uint8_t pitch=17+speex_packet_field(packet,23,7);
    for(uint8_t sub=0;sub<4;sub++) {
        int16_t *exc=frame+40*sub;
        unsigned index=4*(unsigned)speex_packet_field(packet,35+21*(unsigned)sub,5);
        speex_low_unpack(packet,sub,indices);
        if(index && pitch<41) {
            speex_nb3_short_innovation(exc,exc,pitch,indices,scale,index,exc_10_16_table);
        } else {
            int8_t gain[3];
            for(uint8_t i=0;i<3;i++)gain[i]=(int8_t)(32+AVR_READ_I8(gain_cdbk_lbr+index+2-i));
            for(uint8_t v=0;v<4;v++) {
                const int8_t *shape=exc_10_16_table+10*(unsigned)indices[v];
#if SPEEX_NB3_USE_AVR_ASM
                if(index)speex_avr_long_innovation10(exc,exc-pitch-1,shape,scale,gain);
                else speex_avr_zero_innovation10(exc,shape,scale);
#else
                if(index)speex_nb3_long_innovation10_c(exc,exc-pitch-1,shape,scale,gain,10);
                else speex_nb3_zero_innovation_n_c(exc,shape,scale,10);
#endif
                exc+=10;
            }
        }
    }
}
#endif
#endif
