#include <stdint.h>
#include <string.h>
#include "nb3_indices.h"
#include "nb3_header.h"
_Static_assert(!SPEEX_NB3_USE_AVR_ASM,"Independent C reader test");
uint8_t indices_input[42],indices_output[6];
volatile int16_t indices_position,indices_offset,indices_limit,indices_overflow;
volatile int16_t indices_result_position,indices_result_offset,indices_result_overflow;
volatile uint8_t indices_command,indices_status,indices_zero,indices_metadata_ok;
static SpeexBits bits;
static SPEEX_NB3_HOT SPEEX_NB3_NOINLINE void indices_before(SpeexBits *b,uint8_t out[4])
{
    for (uint8_t i=0;i<4;i++) out[i]=(uint8_t)speex_bits_unpack_unsigned(b,5);
}
static SPEEX_NB3_HOT SPEEX_NB3_NOINLINE uint16_t header_before(SpeexBits *b)
{
    const unsigned pitch=speex_bits_unpack_unsigned(b,7);
    const unsigned gain=speex_bits_unpack_unsigned(b,5);
    const unsigned energy=speex_bits_unpack_unsigned(b,1);
    return (uint16_t)((pitch<<6)|(gain<<1)|energy);
}
static SPEEX_NB3_HOT SPEEX_NB3_NOINLINE uint16_t header_after(SpeexBits *b)
{
    return speex_nb3_unpack_header(b);
}
int main(void)
{
    indices_status=1;
    for (;;) {
        while (!indices_command) {}
        memset(&bits,0,sizeof(bits));
        bits.chars=(char *)indices_input+1;
        bits.nbBits=indices_limit;bits.charPtr=indices_position;
        bits.bitPtr=indices_offset;bits.overflow=indices_overflow;
        bits.owner=0x1234;bits.buf_size=40;bits.reserved1=0x1357;
        bits.reserved2=(void *)0x2468;
        memset(indices_output,0xcc,sizeof(indices_output));
        indices_output[0]=0xa5;indices_output[5]=0x5a;
        if (indices_command==1) indices_before(&bits,indices_output+1);
        else if (indices_command==2) speex_nb3_unpack_indices(&bits,indices_output+1);
        else {
            uint16_t header=indices_command==3 ? header_before(&bits) : header_after(&bits);
            indices_output[1]=header>>6;
            indices_output[2]=(header>>1)&31;
            indices_output[3]=header&1;
        }
        __asm__("mov %0,r1":"=r"(indices_zero));
        indices_result_position=bits.charPtr;indices_result_offset=bits.bitPtr;
        indices_result_overflow=bits.overflow;
        indices_metadata_ok=bits.chars==(char *)indices_input+1 && bits.nbBits==indices_limit &&
            bits.owner==0x1234 && bits.buf_size==40 && bits.reserved1==0x1357 && bits.reserved2==(void *)0x2468;
        indices_command=0;indices_status=2;
    }
}
