/* Isolated scalar paths only. No C decoder execution or timing. */
#include "lowrate_noise.h"
void noise_values5_c(int16_t *,int32_t);
void noise_values5_before(int16_t *,int32_t);
volatile int32_t values_scale;
volatile int16_t values_output[7];
volatile uint8_t values_command,values_status;
SPEEX_NB3_STAGE void values_reference(int16_t *out,int32_t scale)
{
    for(int8_t n=-2;n<=2;n++) {
        const int16_t a=(int16_t)n*128;
        const int32_t p=(int32_t)a*(int16_t)(scale>>14)+
            (((int32_t)a*(int16_t)(scale&16383))>>14);
        out[n+2]=(int16_t)(((int32_t)((uint32_t)p<<7)+8192)>>14);
    }
}
int main(void)
{
    values_status=1;
    for(;;)if(values_command) {
        int16_t *out=(int16_t *)values_output+1;
        if(values_command==1)speex_low_noise_values5(out,values_scale);
        else if(values_command==2)noise_values5_c(out,values_scale);
        else if(values_command==3)values_reference(out,values_scale);
        else noise_values5_before(out,values_scale);
        values_command=0;values_status=2;
    }
}
