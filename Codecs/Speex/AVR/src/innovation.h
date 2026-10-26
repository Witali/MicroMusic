#include "nb3_indices.h"
/* Mode 3 has four unsigned 5-bit codebook indices, ten samples each.
 * Fuse the original split_cb_shape_sign_unquant + signal_mul operations:
 * (shape << 9) >> 7 == shape * 4, including negative signed shapes. */
#include "zero_innovation.h"
_Static_assert(SIG_SHIFT==14,"NB3 excitation rounding requires Q14");
extern const signed char exc_10_32_table[];
/* Zero adaptive gain only; no pitch data or temporary buffer is needed. */
#if SPEEX_NB3_USE_AVR_ASM
static
#else
static SPEEX_NB3_STAGE
#endif
void speex_nb3_zero_innovation(spx_word16_t *out,
                                    const uint8_t *input_indices,spx_word32_t scale)
{
#if SPEEX_NB3_USE_AVR_ASM
    const uint8_t *indices=input_indices;
#else
    uint8_t indices[4];
    for(unsigned k=0;k<4;k++)indices[k]=input_indices[k];
#endif
    int vector, sample;
    for (vector = 0; vector < 4; ++vector) {
        unsigned index = indices[vector];
        const signed char *shape = exc_10_32_table + 10*index;
#if SPEEX_NB3_USE_AVR_ASM
        speex_avr_zero_innovation10(out,shape,scale);
        out+=10;
#else
        for (sample = 0; sample < 10; ++sample)
            *out++=speex_nb3_zero_shape_c(AVR_READ_I8(shape+sample),scale);
#endif
    }
}
