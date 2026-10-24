#include <stdint.h>
#include <avr/pgmspace.h>
#include "long_pitch.h"
const int8_t exc_10_32_table[320] PROGMEM={
#include "test-codebook.h"
};
int16_t long40_input[44],long40_output[42];
int8_t long40_gains[5];
uint8_t long40_indices[6];
volatile int32_t long40_scale;
volatile uint8_t long40_command,long40_status,long40_zero;
static SPEEX_NB3_NOINLINE void long40_test_ten(int16_t *out,const int16_t *in,
    const uint8_t *indices,int32_t scale,const int8_t *gain)
{
    uint8_t vector;
    for(vector=0;vector<4;vector++) {
        speex_avr_long_innovation10(out,in,exc_10_32_table+10*indices[vector],scale,gain);
        out+=10;in+=10;
    }
}
static SPEEX_NB3_STAGE_O2 void long40_test_c(int16_t *out,const int16_t *in,
    const uint8_t *indices,int32_t scale,const int8_t *gain)
{
    uint8_t vector;
    for(vector=0;vector<4;vector++) {
        speex_nb3_long_innovation10_c(out,in,exc_10_32_table+10*indices[vector],scale,gain,10);
        out+=10;in+=10;
    }
}
int main(void)
{
    long40_status=1;
    for(;;) {
        while(!long40_command) {}
        if(long40_command==1)
            speex_avr_long_innovation40(long40_output+1,long40_input+1,
                long40_indices+1,long40_scale,long40_gains+1);
        else if(long40_command==2)
            long40_test_ten(long40_output+1,long40_input+1,
                long40_indices+1,long40_scale,long40_gains+1);
        else
            long40_test_c(long40_output+1,long40_input+1,
                long40_indices+1,long40_scale,long40_gains+1);
        __asm__("mov %0,r1":"=r"(long40_zero));
        long40_command=0;long40_status=2;
    }
}
