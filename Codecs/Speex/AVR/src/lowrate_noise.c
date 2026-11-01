/* Adapted from Xiph 1.2.1 math_approx.h / filters.c / nb_celp.c.
 * BSD provenance: vendor/speex-1.2.1/COPYING. No float or new frame buffer.
 * Only rounded innovation words are observable in NB1 vocoder/HB1 folding. */
#include "lowrate_noise.h"
#if SPEEX_ENABLE_NB1
#include "arch.h"
#include "math_approx.h"
#include "lowrate_rng.h"
SPEEX_NB3_NOINLINE void speex_low_noise_values5(int16_t *values,int32_t scale)
{
    /* std=1 has exactly five possible innovations. Scale each once per
     * block, not once per sample. Signed high-word thresholds reproduce
     * PSHR32(r-(r>>3),14) over all 65536 high words, including negatives. */
    values[2]=0;
    for(int8_t noise=-2;noise<=2;noise++)if(noise) {
        int32_t product=MULT16_32_Q14((int16_t)(noise*128),scale);
        values[noise+2]=(int16_t)PSHR32(SHL32(product,7),14);
    }
}
SPEEX_NB3_STAGE void speex_low_noise_indices40(uint8_t *out,uint32_t *seed)
{
    uint32_t next=*seed;
    for(uint8_t i=0;i<40;i++) {
        next=speex_low_rng_next(next);
        int16_t high=(int16_t)(next>>16);
        uint8_t index=high< -9363?(high< -28087?0:1):high<9362?2:high<28086?3:4;
        out[i]=index;
    }
    *seed=next;
}
SPEEX_NB3_STAGE void speex_low_noise_cached40(int16_t *out,const int16_t *cache,uint8_t sub)
{
    /* The low band has already computed all 160 classes and their five
     * scaled values in dead history bytes 0..169. The callback reads one
     * class block; the cache is read-only for the whole synthesis phase. */
    const uint8_t *indices=(const uint8_t *)cache+40*sub;
    const int16_t *values=cache+80;
    for(uint8_t i=0;i<40;i++)out[i]=values[indices[i]];
}
#endif
