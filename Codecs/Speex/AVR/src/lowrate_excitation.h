/* Low-rate frame/controller differences; synthesis stays shared.
 * Adapted from Xiph Speex 1.2.1 nb_celp.c / modes.c (vendor COPYING, BSD).
 * The optional NB2 table shares the existing signed8 LBR pitch gains and
 * 4x10-sample geometry; arithmetic backend selection is unchanged. */
#ifndef MICROMUSIC_SPEEX_LOWRATE_EXCITATION_H
#define MICROMUSIC_SPEEX_LOWRATE_EXCITATION_H
#include "packet_mode.h"
#include "short_pitch.h"
#if SPEEX_ENABLE_NB1
#include "lowrate_noise.h"
#include "math_approx.h"
#endif
extern const int8_t exc_10_16_table[160];
static SPEEX_NB3_NOINLINE void speex_low_unpack(const uint8_t *packet,uint8_t sub,uint8_t indices[4])
{
#if SPEEX_ENABLE_NB8
    if((packet[0]>>3)==8) {
        unsigned at=39+10*(unsigned)sub;
        indices[0]=speex_packet_field(packet,at,5);
        indices[1]=speex_packet_field(packet,at+5,5);
        return;
    }
#endif
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
#if SPEEX_ENABLE_NB8
extern const int8_t exc_20_32_table[640];
/* Forced pitch predicts the complete subframe before innovation is added.
 * For short lags, recompute its at-most-two rounded prediction ancestors
 * from completed history, rather than feeding final innovation back into
 * pitch or allocating a second forty-word excitation buffer. */
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_forced_source(const int16_t *exc,
    uint8_t sample,uint8_t pitch,uint8_t coefficient)
{
    int at=(int)sample-pitch;uint8_t depth=0;
    while(at>=0){at-=pitch;++depth;}
    int16_t value=exc[at];
    while(depth--)value=(int16_t)speex_avr_asr13(
        MULT16_16(value,(int16_t)coefficient<<7)+4096);
    return value;
}
static SPEEX_NB3_STAGE_O2 void speex_nb8_excitation_frame(int16_t *frame,
    const uint8_t *packet,int32_t scale,uint8_t indices[4])
{
    uint8_t pitch=17+speex_packet_field(packet,23,7);
    uint8_t coefficient=(2185L*(int16_t)(speex_packet_field(packet,30,4)<<6)+16384)>>15;
    if(coefficient>63)coefficient=63;
    int8_t gain[3]={0,(int8_t)coefficient,0};int16_t edge[12];
    for(uint8_t sub=0;sub<4;sub++) {
        int16_t *exc=frame+40*sub;uint8_t j=0;
        speex_low_unpack(packet,sub,indices);
        for(uint8_t v=0;v<2;v++) {
            const int8_t *shape=exc_20_32_table+20*(unsigned)indices[v];
            uint8_t left=20;
            while(left) {
                uint8_t count=left>10?10:left;const int16_t *in;
                if(j<pitch-1) {
                    if(count>pitch-1-j)count=pitch-1-j;
                    in=exc+(int)j-pitch-1;
                } else {
                    edge[0]=0;edge[count+1]=0;
                    for(uint8_t k=0;k<count;k++)edge[k+1]=speex_forced_source(exc,j+k,pitch,coefficient);
                    in=edge;
                }
#if SPEEX_NB3_USE_AVR_ASM
                speex_avr_long_innovation_n(exc+j,in,shape,scale,gain,count);
#else
                speex_nb3_long_innovation10_c(exc+j,in,shape,scale,gain,count);
#endif
                shape+=count;j+=count;left-=count;
            }
        }
    }
}
#endif
#if SPEEX_ENABLE_NB1
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_low_q15(int16_t a,int16_t b)
{return speex_avr_asr15_word(MULT16_16(a,b));}
/* NB1's provisional adaptive+innovation sum is overwritten by the vocoder.
 * Keep only its observable rounded noise words and original vocoder state.
 * voc_m2 is used solely as PSHR32(...,14), so retain that exact signed16
 * word instead; voc_m1 retains Q15(.3*previous pulse). Offset stays 0..143;
 * pulse amplitude and gains are frame
 * constants. Original seed progression remains 160 LCG steps per NB1 frame. */
static SPEEX_NB3_STAGE_O2 void speex_nb1_excitation_frame(DecState *st,int16_t *frame,
    const uint8_t *packet,int32_t scale)
{
    uint8_t pitch=17+speex_packet_field(packet,23,7);
    int16_t coefficient=(2185L*(int16_t)(speex_packet_field(packet,30,4)<<6)+16384)>>15;
    int16_t g=(int16_t)((24576L*(coefficient-13)+8192)>>14);
    if(g<0)g=0;if(g>64)g=64;
    int16_t amplitude=(int16_t)((int32_t)spx_sqrt(2*(int16_t)pitch)*
        (int16_t)(((int32_t)g*((scale+8192)>>14)+32)>>6));
    int16_t noise_gain=32767-435*g,previous_gain=77*g;
    int16_t pulse_now=speex_low_q15(22938,amplitude);
    int16_t pulse_previous=speex_low_q15(9830,amplitude);
    int16_t noise[5],current[5],previous[5];
    speex_low_noise_values5(noise,scale);
    for(uint8_t i=0;i<5;i++) {
        current[i]=speex_low_q15(noise_gain,noise[i]);
        previous[i]=speex_low_q15(previous_gain,noise[i]);
    }
    int16_t prior_noise=speex_low_q15(previous_gain,st->voc_previous);
    int16_t prior_pulse=st->voc_m1,mean_state=st->voc_mean;
    uint8_t offset=st->voc_offset,last=2;
    for(uint8_t sub=0;sub<4;sub++) {
        int16_t *exc=frame+40*sub;uint8_t phase=offset;
        uint8_t *symbols=(uint8_t *)exc+40;
        speex_low_noise_indices40(symbols,&st->seed);
        for(uint8_t i=0;i<40;i++) {
            uint8_t is_pulse=i==phase;last=symbols[i];
            if(is_pulse)phase+=pitch;
            int16_t value=(int16_t)(
                (is_pulse?pulse_now:0)+prior_pulse+current[last]-prior_noise);
            prior_pulse=is_pulse?pulse_previous:0;prior_noise=previous[last];
            int32_t mean=MULT16_16(26214,mean_state)+MULT16_16(6554,value)+16384;
            mean_state=speex_avr_asr15_word(mean);
            exc[i]=(int16_t)(value-mean_state);
        }
        offset=phase-40;
    }
    st->voc_offset=offset;st->voc_m1=prior_pulse;st->voc_mean=mean_state;st->voc_previous=noise[last];
}
#endif
#endif
