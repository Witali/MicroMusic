/* Scalar C fallback only; no C decoder is executed or timed. */
#include "lowrate_mean.h"
volatile int16_t mean_old,mean_value,mean_result;
volatile uint8_t mean_command,mean_status;
SPEEX_NB3_STAGE int16_t mean_reference(int16_t old,int16_t value)
{return speex_low_mean_c(old,value);}
int main(void)
{
    mean_status=1;
    for(;;)if(mean_command==1 || mean_command==2) {
        mean_result=mean_command==1?speex_low_mean(mean_old,mean_value):mean_reference(mean_old,mean_value);
        mean_command=0;mean_status=2;
    }
}
