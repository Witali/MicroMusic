#include "lpc_math.h"
#include <stdint.h>
#include <string.h>
volatile uint32_t codec2_math_word;
volatile float codec2_math_output;
volatile uint8_t codec2_math_mode,codec2_math_command,codec2_math_status;
int main(void){
    codec2_math_status=1;
    for(;;)if(codec2_math_command){uint32_t word=codec2_math_word;float angle;memcpy(&angle,&word,4);codec2_math_command=0;
        codec2_math_output=codec2_math_mode==0?codec2_lpc_cosf(angle):codec2_math_mode==1?codec2_lpc_grid_angle((uint16_t)word):codec2_lpc_initial_angle((unsigned)word);
        codec2_math_status=2;__asm__ __volatile__("" ::: "memory");}
}
