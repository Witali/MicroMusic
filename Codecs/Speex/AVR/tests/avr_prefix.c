/* Oracle uses original RAM tables and bit reader; production uses Flash. */
#include <stdint.h>
#include "nb3_lsp.h"
#include "lsp.h"
#include "speex/speex_bits.h"
void reference_lsp_unquant_lbr(spx_lsp_t *,int,SpeexBits *);
unsigned reference_bits_unpack_unsigned(SpeexBits *,int);
uint8_t prefix_packet[22];
int16_t prefix_quarters[12],prefix_reference[12];
volatile uint8_t prefix_gain,prefix_reference_gain,prefix_char,prefix_bit,prefix_overflow;
volatile uint8_t prefix_command,prefix_status;
static SpeexBits bits;
static SPEEX_NB3_STAGE_O2 void prefix_new(const uint8_t *packet,int16_t *out)
{
    speex_nb3_lsp_quarters(packet,out);
    prefix_gain=speex_nb3_frame_gain(packet);
}
int main(void)
{
    prefix_status=1;
    for (;;) {
        while(!prefix_command) {}
        bits=(SpeexBits){0};bits.chars=(char *)prefix_packet+1;bits.nbBits=160;
        bits.buf_size=20;bits.bitPtr=5;
        reference_lsp_unquant_lbr(prefix_reference+1,10,&bits);
        prefix_reference_gain=reference_bits_unpack_unsigned(&bits,5);
        prefix_char=bits.charPtr;prefix_bit=bits.bitPtr;prefix_overflow=bits.overflow;
        prefix_new(prefix_packet+1,prefix_quarters+1);
        prefix_command=0;prefix_status=2;
    }
}
