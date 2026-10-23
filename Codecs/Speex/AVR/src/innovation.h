/* Mode 3 has four unsigned 5-bit codebook indices, ten samples each.
 * Fuse the original split_cb_shape_sign_unquant + signal_mul operations:
 * (shape << 9) >> 7 == shape * 4, including negative signed shapes. */
#include "avr_tables.h"
#include "packed24.h"
extern const signed char exc_10_32_table[];
#if SPEEX_NB3_USE_AVR_ASM
extern void speex_avr_innovation10(int16_t *, const uint8_t *, const int8_t *, int32_t);
#endif
static void speex_avr_innovation(spx_word16_t *out, const uint8_t *pitch,
                                  SpeexBits *bits, spx_word32_t scale)
{
    int vector, sample;
    for (vector = 0; vector < 4; ++vector) {
        unsigned index = speex_bits_unpack_unsigned(bits, 5);
        const signed char *shape = exc_10_32_table + 10*index;
#if SPEEX_NB3_USE_AVR_ASM
        speex_avr_innovation10(out,pitch,shape,scale);
        out+=10;
        pitch+=30;
#else
        for (sample = 0; sample < 10; ++sample) {
            spx_word16_t value = SHL16(AVR_READ_I8(shape + sample), 2);
            spx_word32_t innovation = SHL32(MULT16_32_Q14(value, scale), 7);
            spx_word32_t adaptive = speex_nb3_read24(pitch);
            pitch+=3;
            /* Original clamp +/-262144000, expressed before the common *128. */
            adaptive=SATURATE32(adaptive,2048000);
            *out++ = EXTRACT16(SATURATE32(PSHR32(ADD32(SHL32(adaptive,8),innovation),SIG_SHIFT),32767));
        }
#endif
    }
}
