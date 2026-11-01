/* Isolated zero-innovation primitives; no C decoder execution. */
#include "zero_innovation.h"
extern const int8_t exc_20_32_table[640];
int16_t zero20_output[22];
volatile int32_t zero20_scale;
volatile uint8_t zero20_row,zero20_count,zero20_command,zero20_status;
SPEEX_NB3_STAGE_O2 void zero20_c(int16_t *out,const int8_t *shape,int32_t scale,uint8_t count)
{speex_nb3_zero_innovation_n_c(out,shape,scale,count);}
int main(void)
{
    zero20_status=1;
    for(;;)if(zero20_command) {
        const uint8_t count=zero20_count;
        int16_t *out=count?zero20_output+1:0;
        const int8_t *shape=count?exc_20_32_table+20*(unsigned)zero20_row:0;
        if(zero20_command==1)speex_avr_zero_innovation_n(out,shape,zero20_scale,count);
        else if(zero20_command==2)zero20_c(out,shape,zero20_scale,count);
        else {
            speex_avr_zero_innovation10(out,shape,zero20_scale);
            if(count==20)speex_avr_zero_innovation10(out+10,shape+10,zero20_scale);
        }
        zero20_command=0;zero20_status=2;
    }
}
