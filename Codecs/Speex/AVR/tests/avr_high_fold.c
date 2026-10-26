#include <stdint.h>
#include "wb_fold.h"
uint8_t high_unit_buffer[384],high_unit_indices[5];
volatile uint16_t high_unit_address;
volatile int32_t high_unit_scale,high_unit_gain;
volatile uint8_t high_unit_command,high_unit_status;
int main(void)
{
    high_unit_address=(uint16_t)(uintptr_t)high_unit_buffer;high_unit_status=1;
    for(;;){
        while(!high_unit_command){}
        int16_t *out=(int16_t *)(uintptr_t)high_unit_address;
        if(high_unit_command==1)speex_wb_excitation8_40(out,high_unit_indices,high_unit_scale,high_unit_gain);
        else speex_wb_excitation8_40_c(out,high_unit_indices,high_unit_scale,high_unit_gain);
        high_unit_command=0;high_unit_status=2;
    }
}
