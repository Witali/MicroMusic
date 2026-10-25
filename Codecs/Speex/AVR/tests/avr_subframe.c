#include <stdint.h>
#include "nb3_subframe.h"
#include "nb3_header.h"
#include "nb3_indices.h"

_Static_assert(!SPEEX_NB3_USE_AVR_ASM,"C-only packet reader mailbox");
uint8_t subframe_packet[22],subframe_indices[6];
volatile uint16_t subframe_header;
volatile uint8_t subframe_sub,subframe_command,subframe_status;
volatile uint8_t subframe_char,subframe_bit,subframe_overflow;

static SPEEX_NB3_STAGE_O2 uint16_t subframe_before(SpeexBits *bits,uint8_t indices[4])
{
    uint16_t header=speex_nb3_unpack_header(bits);
    speex_nb3_unpack_indices(bits,indices);
    return header;
}
int main(void)
{
    subframe_status=1;
    for (;;) {
        while (!subframe_command) {}
        if (subframe_command==1) {
            SpeexBits bits={0};
            bits.chars=(char *)subframe_packet+1;bits.nbBits=160;bits.buf_size=20;
            bits.charPtr=3+4*subframe_sub;bits.bitPtr=4+subframe_sub;
            subframe_header=subframe_before(&bits,subframe_indices+1);
            subframe_char=bits.charPtr;subframe_bit=bits.bitPtr;
            subframe_overflow=bits.overflow;
        } else {
            subframe_header=speex_nb3_unpack_subframe(subframe_packet+1,subframe_sub,subframe_indices+1);
        }
        subframe_command=0;subframe_status=2;
    }
}
