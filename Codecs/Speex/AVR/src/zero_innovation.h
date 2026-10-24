/* Exact zero-adaptive excitation for restricted NB3. See nb3_c_math.h for
 * signed8 shape / 0..121000000 scale bounds. C remains selectable on AVR. */
#ifndef MICROMUSIC_ZERO_INNOVATION_H
#define MICROMUSIC_ZERO_INNOVATION_H
#include "avr_tables.h"
#include "nb3_c_math.h"

static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_zero_innovation_n_c(int16_t *out,
    const int8_t *shape,int32_t scale,uint8_t count)
{
    while(count--) *out++=speex_nb3_zero_shape_c(AVR_READ_I8(shape++),scale);
}
#if SPEEX_NB3_USE_AVR_ASM
extern void speex_avr_zero_innovation10(int16_t *,const int8_t *,int32_t);
/* Count 0..10; zero touches no input/output. No history or gain array. */
extern void speex_avr_zero_innovation_n(int16_t *,const int8_t *,int32_t,uint8_t);
#endif
#endif
