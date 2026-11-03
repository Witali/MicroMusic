/* Isolated finite scalar comparison; never executes a C decoder. */
#include "nb1_pitch.h"
volatile uint8_t pitch_value,pitch_command,pitch_status;
volatile int16_t pitch_result;
SPEEX_NB3_STAGE_O2 int16_t pitch_original(uint8_t pitch)
{return speex_nb1_pitch_root_c(pitch);}
SPEEX_NB3_STAGE_O2 int16_t pitch_lookup(uint8_t pitch)
{return speex_nb1_pitch_root_table_c(pitch);}
SPEEX_NB3_STAGE_O2 int16_t pitch_selected(uint8_t pitch)
{return speex_nb1_pitch_root(pitch);}
/* Alternative size recipe, screened rather than retained in the decoder. */
SPEEX_NB3_STAGE_O2 int16_t pitch_threshold(uint8_t p)
{
    if(p<61) {
        if(p<32)return p<25?(p<18?5:6):7;
        return p<41?8:(p<51?9:10);
    }
    if(p<99)return p<85?(p<72?11:12):13;
    return p<128?(p<113?14:15):16;
}
int main(void)
{
    pitch_status=1;
    for(;;)if(pitch_command) {
        uint8_t p=pitch_value;
        if(pitch_command==1)pitch_result=pitch_original(p);
        else if(pitch_command==2)pitch_result=pitch_lookup(p);
        else if(pitch_command==3)pitch_result=pitch_threshold(p);
        else pitch_result=pitch_selected(p);
        pitch_command=0;pitch_status=2;
    }
}
