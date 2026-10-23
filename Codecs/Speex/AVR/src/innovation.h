/* Mode 3 has four unsigned 5-bit codebook indices, ten samples each.
 * Fuse the original split_cb_shape_sign_unquant + signal_mul operations:
 * (shape << 9) >> 7 == shape * 4, including negative signed shapes. */
#include "avr_tables.h"
#include "packed24.h"
extern const signed char exc_10_32_table[];
#if SPEEX_NB3_USE_AVR_ASM
extern void speex_avr_innovation10(int16_t *, const uint8_t *, const int8_t *, int32_t);
#else
#include "nb3_c_math.h"
#endif
static void speex_avr_innovation(spx_word16_t *out, const uint8_t *pitch,
                                  SpeexBits *bits, spx_word32_t scale)
{
    int vector, sample;
#if !SPEEX_NB3_USE_AVR_ASM
    const int16_t scale_high=(int16_t)(scale>>12);
    const int16_t scale_low=(int16_t)(scale&4095);
#endif
    for (vector = 0; vector < 4; ++vector) {
        unsigned index = speex_bits_unpack_unsigned(bits, 5);
        const signed char *shape = exc_10_32_table + 10*index;
#if SPEEX_NB3_USE_AVR_ASM
        speex_avr_innovation10(out,pitch,shape,scale);
        out+=10;
        pitch+=30;
#else
        for (sample = 0; sample < 10; ++sample) {
            spx_word32_t innovation = speex_nb3_shape_scale_c(
                AVR_READ_I8(shape + sample),scale_high,scale_low);
            spx_word32_t adaptive = speex_nb3_read24(pitch);
            pitch+=3;
            /* Original clamp +/-262144000, expressed before the common *128. */
            adaptive=SATURATE32(adaptive,2048000);
            *out++ = EXTRACT16(SATURATE32(PSHR32(ADD32(SHL32(adaptive,8),innovation),SIG_SHIFT),32767));
        }
#endif
    }
}
