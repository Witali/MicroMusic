#include "wb_fold.h"
#include "avr_tables.h"
#include "nb3_c_math.h"
#include "zero_innovation.h"
#include "nb1_cache_layout.h"
extern const int8_t exc_8_128_table[1024];
extern const int8_t exc_10_32_table[320];
#if SPEEX_ENABLE_NB2 || SPEEX_ENABLE_NB8
extern const int8_t exc_10_16_table[160];
extern const int8_t exc_20_32_table[640];
/* Explicit C reference keeps separate reconstruction and folding, including
 * the original intermediate word and both quantizers on every target. */
SPEEX_NB3_STAGE void speex_wb_excitation_low40_c(int16_t *exc,const uint8_t *indices,int32_t scale,int32_t g,uint8_t mode)
{
    const int8_t *table;uint8_t vectors,width;
#if SPEEX_ENABLE_NB2
    if(mode==2){table=exc_10_16_table;vectors=4;width=10;}else
#endif
#if SPEEX_ENABLE_NB8
    {table=exc_20_32_table;vectors=2;width=20;}
#else
    {table=exc_10_16_table;vectors=4;width=10;}
#endif
    for(uint8_t v=0;v<vectors;v++) {
        const int8_t *shape=table+width*(unsigned)indices[v];
        for(uint8_t at=0;at<width;at+=10) {
            speex_nb3_zero_innovation_n_c(exc+width*v+at,shape+at,scale,10);
        }
    }
    speex_wb_fold40_c(exc,g);
}
#endif
/* g is the original HB1 exp gain divided by the filter ratio.
 * Keep the two distinct quantization/rounding steps; combining their gains
 * changes PCM. Unsigned product arithmetic preserves modulo32 behavior. */
static SPEEX_NB3_ALWAYS_INLINE int16_t scale_sample(int16_t t,int32_t g,unsigned odd)
{
    uint16_t r=(uint16_t)(((uint32_t)t*(uint32_t)g+256)>>9);
    return (int16_t)(odd?(uint16_t)(0u-r):r);
}
static SPEEX_NB3_ALWAYS_INLINE int16_t fold_sample(int16_t v,int32_t g,unsigned odd)
{return scale_sample((int16_t)(((int32_t)29491*v)>>15),g,odd);}
#if SPEEX_ENABLE_NB1
void speex_wb_fold5_c(int16_t *table,int32_t g)
{
    for(uint8_t i=0;i<5;i++)table[i]=fold_sample(table[i],g,0);
}
void speex_wb_noise_scale5_c(int16_t *table,int32_t g)
{
    for(uint8_t i=0;i<5;i++)table[i]=i==2?0:scale_sample(table[i],g,0);
}
typedef void (*Fold5)(int16_t *,int32_t);
static SPEEX_NB3_ALWAYS_INLINE void noise_fold40(int16_t *out,const int16_t *cache,
    uint8_t sub,int32_t g,int16_t *scratch,Fold5 fold)
{
    for(uint8_t i=0;i<5;i++)scratch[i]=cache[SPEEX_NB1_PREFOLD_WORD+i];
    fold(scratch,g);
    const uint8_t *classes=(const uint8_t *)cache+40*sub;
    for(uint8_t i=0;i<40;i++) {
        const uint16_t value=(uint16_t)scratch[classes[i]];
        out[i]=(int16_t)((i&1)?(uint16_t)(0u-value):value);
    }
}
SPEEX_NB3_STAGE_O2 void speex_wb_noise_fold40_c(int16_t *out,const int16_t *cache,
    uint8_t sub,int32_t g,int16_t *scratch)
{noise_fold40(out,cache,sub,g,scratch,speex_wb_noise_scale5_c);}
#if SPEEX_NB3_USE_AVR_ASM
SPEEX_NB3_STAGE_O2 void speex_wb_noise_fold40_avr(int16_t *out,const int16_t *cache,
    uint8_t sub,int32_t g,int16_t *scratch)
{noise_fold40(out,cache,sub,g,scratch,speex_wb_noise_scale5_avr);}
#endif
#endif
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
