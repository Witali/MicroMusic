/* Isolated scalar arithmetic only; no C decoder execution. */
#include "forced_math.h"
#include "avr_shift.h"
volatile int16_t forced_math_x,forced_math_result;
volatile uint8_t forced_math_c,forced_math_code,forced_math_command,forced_math_status;
SPEEX_NB3_STAGE_O2 int16_t forced_math_selected(int16_t x,uint8_t c)
{return speex_forced_q6(x,c);}
SPEEX_NB3_STAGE_O2 int16_t forced_math_c_reference(int16_t x,uint8_t c)
{return speex_forced_q6_c(x,c);}
SPEEX_NB3_STAGE_O2 int16_t forced_math_original(int16_t x,uint8_t c)
{return (int16_t)speex_avr_asr13((int32_t)x*((int16_t)c<<7)+4096);}
SPEEX_NB3_STAGE_O2 uint8_t forced_math_coefficient(uint8_t code)
{return speex_forced_coefficient_c(code);}
SPEEX_NB3_STAGE_O2 uint8_t forced_math_original_coefficient(uint8_t code)
{return (2185L*(int16_t)(code<<6)+16384)>>15;}
int main(void)
{
    forced_math_status=1;
    for(;;)if(forced_math_command) {
        const uint8_t command=forced_math_command;
        if(command==1)forced_math_result=forced_math_selected(forced_math_x,forced_math_c);
        else if(command==2)forced_math_result=forced_math_c_reference(forced_math_x,forced_math_c);
        else if(command==3)forced_math_result=forced_math_original(forced_math_x,forced_math_c);
        else if(command==4)forced_math_result=forced_math_coefficient(forced_math_code);
        else forced_math_result=forced_math_original_coefficient(forced_math_code);
        forced_math_command=0;forced_math_status=2;
    }
}
