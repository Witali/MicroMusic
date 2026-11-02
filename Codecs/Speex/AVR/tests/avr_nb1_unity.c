/* Isolated C scalar arithmetic only; no C decoder execution. */
#include "nb1_zero_gain.h"
volatile int16_t unity_input,unity_result;
volatile uint8_t unity_command,unity_status;
SPEEX_NB3_STAGE_O2 int16_t unity_original(int16_t n)
{return (int16_t)(((int32_t)32767*n)>>15);}
SPEEX_NB3_STAGE_O2 int16_t unity_generic(int16_t n)
{return speex_nb1_unity_q15_c(n);}
SPEEX_NB3_STAGE_O2 int16_t unity_noise(int16_t n)
{return speex_nb1_noise_unity_c(n);}
int main(void)
{
    unity_status=1;
    for(;;)if(unity_command) {
        int16_t n=unity_input;
        if(unity_command==1)unity_result=unity_original(n);
        else if(unity_command==2)unity_result=unity_generic(n);
        else unity_result=unity_noise(n);
        unity_command=0;unity_status=2;
    }
}
