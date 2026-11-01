/* Isolated scalar arithmetic; this is not a C decoder runtime test. */
#include "wb_gain_div.h"
volatile int32_t gain_energy,gain_result;
volatile int16_t gain_ratio;
volatile uint8_t gain_command,gain_status;
SPEEX_NB3_STAGE int32_t gain_reference(int32_t energy,int16_t ratio)
{ return speex_wb_gain_div_c(energy,ratio); }
int main(void)
{
    gain_status=1;
    for(;;) {
        if(gain_command==1 || gain_command==2) {
            gain_result=gain_command==1?speex_wb_gain_div(gain_energy,gain_ratio):gain_reference(gain_energy,gain_ratio);
            gain_command=0;gain_status=2;
        }
    }
}
