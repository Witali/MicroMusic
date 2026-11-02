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
#include "lowrate_mean.h"
#include "nb1_vocoder.h"
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
#include "forced_pitch.h"
#include "forced_math.h"
extern const int8_t exc_20_32_table[640];
/* Forced coefficient 0 has no adaptive contribution, including short-lag
 * ancestors. Reuse the exact zero primitive on complete twenty-word rows. */
static SPEEX_NB3_STAGE_O2 void speex_nb8_zero_frame(int16_t *frame,
    const uint8_t *packet,int32_t scale,uint8_t indices[4])
{
    for(uint8_t sub=0;sub<4;sub++) {
        speex_low_unpack(packet,sub,indices);
        for(uint8_t v=0;v<2;v++) {
            const int8_t *shape=exc_20_32_table+20*(unsigned)indices[v];
#if SPEEX_NB3_USE_AVR_ASM
            speex_avr_zero_innovation_n(frame,shape,scale,20);
#else
            speex_nb3_zero_innovation_n_c(frame,shape,scale,20);
#endif
            frame+=20;
        }
    }
}
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
    while(depth--)value=speex_forced_q6(value,coefficient);
    return value;
}
static SPEEX_NB3_STAGE_O2 void speex_nb8_excitation_frame(int16_t *frame,
    const uint8_t *packet,int32_t scale,uint8_t indices[4])
{
    const uint8_t coded_coefficient=speex_packet_field(packet,30,4);
    /* Sixteen codes produce 0..64 (clamped to63); only code0 produces0.
     * Test it before computing a coefficient or reading the unused pitch. */
    if(!coded_coefficient){speex_nb8_zero_frame(frame,packet,scale,indices);return;}
    uint8_t coefficient=speex_forced_coefficient_c(coded_coefficient);
    if(coefficient>63)coefficient=63;
    uint8_t pitch=17+speex_packet_field(packet,23,7);
    int16_t edge[10];
    for(uint8_t sub=0;sub<4;sub++) {
        int16_t *exc=frame+40*sub;uint8_t j=0;
        speex_low_unpack(packet,sub,indices);
        for(uint8_t v=0;v<2;v++) {
            const int8_t *shape=exc_20_32_table+20*(unsigned)indices[v];
            uint8_t left=20;
            while(left) {
                uint8_t count=left>10?10:left;const int16_t *in;
                if(j<pitch) {
                    if(count>pitch-j)count=pitch-j;
                    in=exc+(int)j-pitch;
                } else {
                    for(uint8_t k=0;k<count;k++)edge[k]=speex_forced_source(exc,j+k,pitch,coefficient);
                    in=edge;
                }
#if SPEEX_NB3_USE_AVR_ASM
                speex_avr_forced_innovation_n(exc+j,in,shape,scale,coefficient,count);
#else
                speex_forced_innovation_n_c(exc+j,in,shape,scale,coefficient,count);
#endif
                shape+=count;j+=count;left-=count;
            }
        }
    }
}
#endif
#if SPEEX_ENABLE_NB1
#include "nb1_gain.h"
#include "nb1_zero_gain.h"
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_low_q15(int16_t a,int16_t b)
{return speex_avr_asr15_word(MULT16_16(a,b));}
/* NB1's provisional adaptive+innovation sum is overwritten by the vocoder.
 * Keep only its observable rounded noise words and original vocoder state.
 * voc_m2 is used solely as PSHR32(...,14), so retain that exact signed16
 * word instead; voc_m1 retains Q15(.3*previous pulse). Offset stays 0..143;
 * pulse amplitude and gains are frame
 * constants. Original seed progression remains 160 LCG steps per NB1 frame. */
#if SPEEX_ENABLE_WB1
static SPEEX_NB3_STAGE_O2 void speex_nb1_excitation_prepare(DecState *st,
    const uint8_t *packet,int32_t scale)
#else
static SPEEX_NB3_STAGE_O2 void speex_nb1_excitation_frame(DecState *st,int16_t *frame,
    const uint8_t *packet,int32_t scale)
#endif
{
    uint8_t pitch=17+speex_packet_field(packet,23,7);
    int16_t g=speex_nb1_gain_selected_c(speex_packet_field(packet,30,4));
    int16_t noise_gain=32767,previous_gain=0,pulse_now=0,pulse_previous=0;
    if(g) {
        int16_t amplitude=(int16_t)((int32_t)spx_sqrt(2*(int16_t)pitch)*
            (int16_t)(((int32_t)g*((scale+8192)>>14)+32)>>6));
        noise_gain=32767-435*g;previous_gain=77*g;
        pulse_now=speex_low_q15(22938,amplitude);
        pulse_previous=speex_low_q15(9830,amplitude);
    }
#if SPEEX_ENABLE_WB1
    /* Synthesis starts at history word OFFSET-40 (105 in this profile).
     * Cache 160 byte classes and five word values before that live suffix.
     * Next frame's history move reads from word 160, beyond the cache too.
     * NB1 vocoder construction itself never reads adaptive pitch history. */
    _Static_assert(NB_FRAME_SIZE==160 && NB_SUBFRAME_SIZE==40,
                   "Noise cache uses the fixed NB frame/subframe geometry");
    _Static_assert(2*(NB_DEC_EXC_OFFSET-NB_SUBFRAME_SIZE)>=SPEEX_NB1_WORK_BYTES,
                   "Vocoder context must precede delayed synthesis history");
    _Static_assert(2*NB_FRAME_SIZE>=SPEEX_NB1_WORK_BYTES,
                   "Vocoder context must precede next history move source");
    int16_t *noise=st->excBuf+SPEEX_NB1_VALUES_WORD;
    int16_t *context=st->excBuf+SPEEX_NB1_CONTEXT_WORD;
    int16_t *current=context+SPEEX_NB1_CURRENT,*previous=context+SPEEX_NB1_PREVIOUS;
    int16_t *prefold=st->excBuf+SPEEX_NB1_PREFOLD_WORD;
#else
    int16_t noise[5];
    int16_t current[5],previous[5];
#endif
    speex_low_noise_values5(noise,scale);
    if(g) {
        for(uint8_t i=0;i<5;i++) {
            current[i]=speex_low_q15(noise_gain,noise[i]);
            previous[i]=speex_low_q15(previous_gain,noise[i]);
        }
    } else {
        for(uint8_t i=0;i<5;i++) {
            current[i]=speex_nb1_noise_unity_c(noise[i]);previous[i]=0;
        }
    }
#if SPEEX_ENABLE_WB1
    for(uint8_t i=0;i<5;i++)prefold[i]=i==2?0:speex_low_q15(29491,noise[i]);
#endif
    int16_t prior_noise=g?speex_low_q15(previous_gain,st->voc_previous):0;
#if SPEEX_ENABLE_WB1
    context[SPEEX_NB1_PULSE_NOW]=pulse_now;
    context[SPEEX_NB1_PULSE_PREVIOUS]=pulse_previous;
    context[SPEEX_NB1_PRIOR_NOISE]=prior_noise;
    context[SPEEX_NB1_PITCH]=pitch;
#else
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
            mean_state=speex_low_mean(mean_state,value);
            exc[i]=(int16_t)(value-mean_state);
        }
        offset=phase-40;
    }
    st->voc_offset=offset;st->voc_m1=prior_pulse;st->voc_mean=mean_state;st->voc_previous=noise[last];
#endif
}
#if SPEEX_ENABLE_WB1
/* Current excitation is needed by the next quarter's delayed IIR input.
 * Build only this quarter now; keep constants in dead history words85..98.
 * Every final vocoder word/seed is unchanged; no additional RAM is allocated. */
static SPEEX_NB3_STAGE_O2 void speex_nb1_excitation_subframe(DecState *st,int16_t *exc,uint8_t sub)
{
    int16_t *context=st->excBuf+SPEEX_NB1_CONTEXT_WORD;
    SpeexNb1Cursor cursor={st->voc_m1,context[SPEEX_NB1_PRIOR_NOISE],st->voc_mean,st->voc_offset,2};
    uint8_t *symbols=(uint8_t *)st->excBuf+40*sub;
    speex_low_noise_indices40(symbols,&st->seed);
    if(speex_nb1_context_is_zero(context))speex_nb1_synthesize40_zero(exc,symbols,context,&cursor);
    else speex_nb1_synthesize40(exc,symbols,context,&cursor);
    st->voc_offset=cursor.phase;st->voc_m1=cursor.prior_pulse;st->voc_mean=cursor.mean;
    st->voc_previous=st->excBuf[SPEEX_NB1_VALUES_WORD+cursor.last];
    context[SPEEX_NB1_PRIOR_NOISE]=cursor.prior_noise;
}
#endif
#endif
#endif
