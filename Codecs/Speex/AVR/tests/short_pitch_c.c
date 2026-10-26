/* Compile this translation unit with the real AVR target and ASM disabled. */
#define speex_nb3_short_innovation speex_nb3_short_innovation_c_test
#include "short_pitch.h"
void short_c_test(int16_t *out,const int16_t *exc,uint8_t pitch,SpeexBits *bits,
                  int32_t scale,unsigned gain)
{
    uint8_t indices[4];
    speex_nb3_unpack_indices(bits,indices);
    speex_nb3_short_innovation(out,exc,pitch,indices,scale,gain);
}
