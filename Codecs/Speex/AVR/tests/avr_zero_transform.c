#include <stdint.h>
#include <avr/pgmspace.h>
static const int8_t shapes[] PROGMEM={
#include "test-shapes.h"
};
int16_t zero_output[12];
uint8_t zero_packed[32];
volatile int32_t zero_scale;
volatile uint8_t zero_index,zero_command,zero_status,zero_r1;
extern void speex_avr_zero_innovation10(int16_t *,const int8_t *,int32_t);
extern void speex_avr_innovation10(int16_t *,const uint8_t *,const int8_t *,int32_t);
extern void zero_transform_c(int16_t *,const int8_t *,int32_t);
int main(void)
{
    zero_status=1;
    for (;;) {
        while (!zero_command) {}
        if (zero_command==1)
            speex_avr_zero_innovation10(zero_output+1,shapes+zero_index,zero_scale);
        else if (zero_command==2)
            zero_transform_c(zero_output+1,shapes+zero_index,zero_scale);
        else
            speex_avr_innovation10(zero_output+1,zero_packed+1,shapes+zero_index,zero_scale);
        __asm__("mov %0,r1":"=r"(zero_r1));
        zero_command=0;zero_status=2;
    }
}
