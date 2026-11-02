/* Isolated C scalar controls only; no C decoder execution. */
#include "nb1_gain.h"
volatile uint8_t nb1_gain_code,nb1_gain_result,nb1_gain_command,nb1_gain_status;
SPEEX_NB3_STAGE_O2 uint8_t nb1_gain_original(uint8_t code)
{
    int16_t c=(2185L*(int16_t)(code<<6)+16384)>>15;
    int16_t g=(int16_t)((24576L*(c-13)+8192)>>14);
    if(g<0)g=0;if(g>64)g=64;return (uint8_t)g;
}
SPEEX_NB3_STAGE_O2 uint8_t nb1_gain_coefficient(uint8_t code)
{
    int16_t c=speex_forced_coefficient_c(code);
    int16_t g=(int16_t)((24576L*(c-13)+8192)>>14);
    if(g<0)g=0;if(g>64)g=64;return (uint8_t)g;
}
SPEEX_NB3_STAGE_O2 uint8_t nb1_gain_factored(uint8_t code)
{return speex_nb1_gain_c(code);}
SPEEX_NB3_STAGE_O2 uint8_t nb1_gain_lookup(uint8_t code)
{return speex_nb1_gain_table_c(code);}
SPEEX_NB3_STAGE_O2 uint8_t nb1_gain_bounded_lookup(uint8_t code)
{return speex_nb1_gain_bounded_table_c(code);}
int main(void)
{
    nb1_gain_status=1;
    for(;;)if(nb1_gain_command) {
        uint8_t code=nb1_gain_code;
        if(nb1_gain_command==1)nb1_gain_result=nb1_gain_original(code);
        else if(nb1_gain_command==2)nb1_gain_result=nb1_gain_coefficient(code);
        else if(nb1_gain_command==3)nb1_gain_result=nb1_gain_factored(code);
        else if(nb1_gain_command==4)nb1_gain_result=nb1_gain_lookup(code);
        else nb1_gain_result=nb1_gain_bounded_lookup(code);
        nb1_gain_command=0;nb1_gain_status=2;
    }
}
