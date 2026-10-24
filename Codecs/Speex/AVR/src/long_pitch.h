/* Exact long-pitch/innovation fusion for restricted Xiph Speex NB3.
 * Sources must be 12 completed signed16 history samples for each ten outputs.
 * Gains are three signed8 values with L1 norm <=147: every sum fits signed24.
 * Preserve the upstream pitch clamp, Q14 floors, rounding and output clamp. */
#ifndef MICROMUSIC_NB3_LONG_PITCH_H
#define MICROMUSIC_NB3_LONG_PITCH_H
#include "speex_platform.h"
#include "avr_tables.h"
#include "nb3_c_math.h"

/* Inline into the O2 forty-sample caller to share gain/scale setup without
 * expanding ten large MAC bodies. C remains selectable on AVR. */
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_long_innovation10_c(int16_t *out,
    const int16_t *in,const int8_t *shape,int32_t scale,const int8_t *gain,uint8_t count)
{
    const int16_t high=(int16_t)(scale>>12),low=(int16_t)(scale&4095);
    const int8_t g0=gain[0],g1=gain[1],g2=gain[2];
    int16_t a=*in++,b=*in++;
    while (count--) {
        int16_t c=*in++;
        int32_t adaptive=(int32_t)g0*a+(int32_t)g1*b+(int32_t)g2*c;
        int32_t innovation=speex_nb3_shape_scale_c(AVR_READ_I8(shape++),high,low);
        a=b;b=c;
        if (adaptive>2048000) adaptive=2048000;
        if (adaptive<-2048000) adaptive=-2048000;
        *out++=speex_nb3_saturating_q14_c(
            (int32_t)(((uint32_t)adaptive<<8)+(uint32_t)innovation+8192));
    }
}
#if SPEEX_NB3_USE_AVR_ASM
extern void speex_avr_long_innovation10(int16_t *,const int16_t *,const int8_t *,
                                        int32_t,const int8_t *);
/* count 0..10; a nonempty block reads count+2 completed history words.
 * Zero returns without touching the data. The fixed-ten entry stays fast. */
extern void speex_avr_long_innovation_n(int16_t *,const int16_t *,const int8_t *,
                                        int32_t,const int8_t *,uint8_t);
#endif
#endif
