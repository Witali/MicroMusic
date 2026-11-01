/* Exact one-tap forced prediction for Xiph Speex submode 8.
 * Adapted from the shared long-pitch transform; retain vendor BSD notices.
 * Coefficient 0..63, signed16 completed history, scale 0..121000000,
 * count 0..10. Keep the pitch clamp and original innovation quantization. */
#ifndef MICROMUSIC_SPEEX_FORCED_PITCH_H
#define MICROMUSIC_SPEEX_FORCED_PITCH_H
#include "long_pitch.h"

static SPEEX_NB3_ALWAYS_INLINE void speex_forced_innovation_n_c(int16_t *out,
    const int16_t *history,const int8_t *shape,int32_t scale,uint8_t coefficient,uint8_t count)
{
    const int16_t high=(int16_t)(scale>>12),low=(int16_t)(scale&4095);
    while(count--) {
        int32_t adaptive=(int32_t)coefficient * *history++;
        int32_t innovation=speex_nb3_shape_scale_c(AVR_READ_I8(shape++),high,low);
        if(adaptive>2048000)adaptive=2048000;
        if(adaptive<-2048000)adaptive=-2048000;
        *out++=speex_nb3_saturating_q14_c(
            (int32_t)(((uint32_t)adaptive<<8)+(uint32_t)innovation+8192));
    }
}
#if SPEEX_NB3_USE_AVR_ASM
extern void speex_avr_forced_innovation_n(int16_t *,const int16_t *,const int8_t *,
                                         int32_t,uint8_t,uint8_t);
#endif
#endif
