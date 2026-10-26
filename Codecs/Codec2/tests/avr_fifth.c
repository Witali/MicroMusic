#include "fixed_fifth.h"
#include <math.h>
#include <stdint.h>
volatile float codec2_root_input,codec2_root_output;
volatile uint8_t codec2_root_command,codec2_root_status;
int main(void){
    codec2_root_status=1;
    for(;;)if(codec2_root_command){
        codec2_root_command=0;
#if CODEC2_BENCH_FLOAT
        codec2_root_output=powf(codec2_root_input,.2f);
#else
        codec2_root_output=codec2_fixed_fifth(codec2_root_input);
#endif
        codec2_root_status=2;
        __asm__ __volatile__("" ::: "memory");
    }
}
