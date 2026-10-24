#include <stdint.h>
#include <avr/pgmspace.h>
#include "long_pitch.h"
static const int8_t shapes[] PROGMEM={
#include "test-shapes.h"
};
int16_t long_input[14],long_output[12];
int8_t long_gains[5];
uint8_t long_packed[32];
extern void speex_avr_innovation10(int16_t *,const uint8_t *,const int8_t *,int32_t);
volatile int32_t long_scale;
volatile uint8_t long_index,long_command,long_status,long_zero;
static SPEEX_NB3_STAGE_O2 void long_test_c(int16_t *out,const int16_t *in,
    const int8_t *shape,int32_t scale,const int8_t *gain)
{
    speex_nb3_long_innovation10_c(out,in,shape,scale,gain,10);
}
int main(void)
{
    long_status=1;
    for (;;) {
        while (!long_command) {}
        if (long_command==1)
            speex_avr_long_innovation10(long_output+1,long_input+1,
                shapes+long_index,long_scale,long_gains+1);
        else if (long_command==2)
            long_test_c(long_output+1,long_input+1,
                shapes+long_index,long_scale,long_gains+1);
        else
            speex_avr_innovation10(long_output+1,long_packed+1,
                shapes+long_index,long_scale);
        __asm__("mov %0,r1":"=r"(long_zero));
        long_command=0;long_status=2;
    }
}
