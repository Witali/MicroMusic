#include <stdint.h>
#include "avr_tables.h"
#include "zero_innovation.h"
_Static_assert(!SPEEX_NB3_USE_AVR_ASM,"This worker explicitly selects portable C");
SPEEX_NB3_STAGE_O2 void zero_transform_c(int16_t *out,const int8_t *shape,int32_t scale)
{
    uint8_t count=10;
    do { *out++=speex_nb3_zero_shape_c(AVR_READ_I8(shape++),scale); } while (--count);
}
SPEEX_NB3_STAGE_O2 void zero_transform_c_n(int16_t *out,const int8_t *shape,
                                        int32_t scale,uint8_t count)
{
    speex_nb3_zero_innovation_n_c(out,shape,scale,count);
}
