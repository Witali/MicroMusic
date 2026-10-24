/* Mode 3 has four unsigned 5-bit codebook indices, ten samples each.
 * Fuse the original split_cb_shape_sign_unquant + signal_mul operations:
 * (shape << 9) >> 7 == shape * 4, including negative signed shapes. */
#include "avr_tables.h"
_Static_assert(SIG_SHIFT==14,"NB3 excitation rounding requires Q14");
extern const signed char exc_10_32_table[];
#if SPEEX_NB3_USE_AVR_ASM
extern void speex_avr_zero_innovation10(int16_t *,const int8_t *,int32_t);
#else
#include "nb3_c_math.h"
#endif
/* Zero adaptive gain only; no pitch data or temporary buffer is needed. */
#if SPEEX_NB3_USE_AVR_ASM
static
#else
static SPEEX_NB3_STAGE
#endif
void speex_nb3_zero_innovation(spx_word16_t *out,
                                    SpeexBits *bits,spx_word32_t scale)
{
    int vector, sample;
    for (vector = 0; vector < 4; ++vector) {
        unsigned index = speex_bits_unpack_unsigned(bits, 5);
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
