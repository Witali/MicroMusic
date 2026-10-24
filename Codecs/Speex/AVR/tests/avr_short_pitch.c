#include <stdint.h>
#include <string.h>
#include "short_pitch.h"
int16_t short_exc[83]; /* guard, 41 history words, 40 outputs, guard */
uint8_t short_packet[5]; /* guard, twenty bits, guard */
volatile uint8_t short_pitch,short_gain,short_command,short_status,short_zero;
volatile uint8_t short_char,short_bit,short_overflow;
volatile int32_t short_scale;
extern void short_c_test(int16_t *,const int16_t *,uint8_t,SpeexBits *,int32_t,unsigned);
int main(void)
{
    short_status=1;
    for (;;) {
        SpeexBits bits;
        while(!short_command) {}
        memset(&bits,0,sizeof(bits));
        bits.chars=(char *)(short_packet+1);bits.nbBits=20;bits.buf_size=3;
        if(short_command==1)
            speex_nb3_short_innovation(short_exc+42,short_exc+42,short_pitch,
                                      &bits,short_scale,(unsigned)short_gain*4);
        else
            short_c_test(short_exc+42,short_exc+42,short_pitch,
                         &bits,short_scale,(unsigned)short_gain*4);
        __asm__("mov %0,r1":"=r"(short_zero));
        short_char=bits.charPtr;short_bit=bits.bitPtr;short_overflow=bits.overflow;
        short_command=0;short_status=2;
    }
}
