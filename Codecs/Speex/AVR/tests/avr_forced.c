/* Isolated C/ASM one-tap arithmetic and unchanged three-tap controls. */
#include "forced_pitch.h"
extern const int8_t exc_20_32_table[640];
int16_t forced_history[12],forced_output[12];
volatile int32_t forced_scale;
volatile uint8_t forced_row,forced_offset,forced_count,forced_coefficient,forced_command,forced_status;
SPEEX_NB3_STAGE_O2 void forced_c(int16_t *out,const int16_t *in,const int8_t *shape,
                               int32_t scale,uint8_t coefficient,uint8_t count)
{speex_forced_innovation_n_c(out,in,shape,scale,coefficient,count);}
SPEEX_NB3_STAGE_O2 void forced_old_c(int16_t *out,const int16_t *in,const int8_t *shape,
                                   int32_t scale,const int8_t *gain,uint8_t count)
{speex_nb3_long_innovation10_c(out,in,shape,scale,gain,count);}
int main(void)
{
    forced_status=1;
    for(;;)if(forced_command) {
        const uint8_t count=forced_count,coefficient=forced_coefficient;
        int16_t *out=count?forced_output+1:0;
        const int16_t *in=count?forced_history+1:0;
        const int8_t *shape=count?exc_20_32_table+20*(unsigned)forced_row+forced_offset:0;
        int8_t gains[3]={0,(int8_t)coefficient,0};
        if(forced_command==1)speex_avr_forced_innovation_n(out,in,shape,forced_scale,coefficient,count);
        else if(forced_command==2)forced_c(out,in,shape,forced_scale,coefficient,count);
        else if(forced_command==3)speex_avr_long_innovation_n(out,forced_history,shape,forced_scale,gains,count);
        else forced_old_c(out,forced_history,shape,forced_scale,gains,count);
        forced_command=0;forced_status=2;
    }
}
