#include "wb_fold.h"
#include "avr_tables.h"
#include "nb3_c_math.h"
#include "zero_innovation.h"
extern const int8_t exc_8_128_table[1024];
extern const int8_t exc_10_32_table[320];
/* g is the original HB1 exp gain divided by the filter ratio.
 * Keep the two distinct quantization/rounding steps; combining their gains
 * changes PCM. Unsigned product arithmetic preserves modulo32 behavior. */
static SPEEX_NB3_ALWAYS_INLINE int16_t fold_sample(int16_t v,int32_t g,unsigned odd)
{
    int16_t t=(int16_t)(((int32_t)29491*v)>>15);
    uint16_t r=(uint16_t)(((uint32_t)t*(uint32_t)g+256)>>9);
    return (int16_t)(odd?(uint16_t)(0u-r):r);
}
SPEEX_NB3_HOT void speex_wb_fold40_c(int16_t *exc,int32_t g)
{
    for(unsigned i=0;i<40;i++)exc[i]=fold_sample(exc[i],g,i&1);
}
/* Private fixed NB3 codebook layout: four indices, ten samples each.
 * Inputs are read-only and must not overlap the forty-word output.
 * 0<=scale<=121000000; same domain as zero-adaptive NB3 excitation. */
SPEEX_NB3_HOT void speex_wb_excitation40_c(int16_t *exc,const uint8_t *indices,int32_t scale,int32_t g)
{
    for(unsigned vector=0;vector<4;vector++) {
        const int8_t *shape=exc_10_32_table+10*indices[vector];
        for(unsigned i=0;i<10;i++) {
            int16_t v=speex_nb3_zero_shape_c(AVR_READ_I8(shape+i),scale);
            *exc++=fold_sample(v,g,i&1);
        }
    }
}

/* Explicit C reference: separate original quantization then folding,
 * using the existing forty-word output as the intermediate buffer. */
SPEEX_NB3_HOT void speex_wb_excitation8_40_c(int16_t *exc,const uint8_t *indices,int32_t scale,int32_t g)
{
    for(unsigned vector=0;vector<5;vector++) {
        const int8_t *shape=exc_8_128_table+8*(unsigned)indices[vector];
        speex_nb3_zero_innovation_n_c(exc+8*vector,shape,scale,8);
    }
    speex_wb_fold40_c(exc,g);
}
