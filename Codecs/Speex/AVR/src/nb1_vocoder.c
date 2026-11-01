/* Original Xiph NB1 loop arithmetic; see vendor/speex-1.2.1/COPYING.
 * Explicit C primitive, also selectable on AVR with assembly disabled. */
#include "nb1_vocoder.h"
#include "lowrate_mean.h"
#if SPEEX_ENABLE_NB1 && SPEEX_ENABLE_WB1
void speex_nb1_synthesize40_c(int16_t *out,const uint8_t *symbols,
    const int16_t *context,SpeexNb1Cursor *cursor)
{
    int16_t prior_pulse=cursor->prior_pulse,prior_noise=cursor->prior_noise,mean=cursor->mean;
    uint8_t phase=cursor->phase,last=2,pitch=(uint8_t)context[SPEEX_NB1_PITCH];
    for(uint8_t i=0;i<40;i++) {
        uint8_t pulse=i==phase;last=symbols[i];
        if(pulse)phase+=pitch;
        int16_t value=(int16_t)((pulse?context[SPEEX_NB1_PULSE_NOW]:0)+prior_pulse+
            context[SPEEX_NB1_CURRENT+last]-prior_noise);
        prior_pulse=pulse?context[SPEEX_NB1_PULSE_PREVIOUS]:0;
        prior_noise=context[SPEEX_NB1_PREVIOUS+last];
        mean=speex_low_mean_c(mean,value);
        out[i]=(int16_t)(value-mean);
    }
    cursor->prior_pulse=prior_pulse;cursor->prior_noise=prior_noise;cursor->mean=mean;
    cursor->phase=phase-40;cursor->last=last;
}
#endif
