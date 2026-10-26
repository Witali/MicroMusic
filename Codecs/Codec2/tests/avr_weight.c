#include "fixed_weight.h"
#include <stdint.h>
volatile float codec2_weight_input[11];
compact_complex codec2_weight_output[256];
volatile uint8_t codec2_weight_command,codec2_weight_status;
int main(void){
    codec2_weight_status=1;
    for(;;)if(codec2_weight_command){
        float a[11];codec2_weight state;codec2_weight_command=0;
        for(unsigned i=0;i<11;++i)a[i]=codec2_weight_input[i];
        codec2_weight_init(&state,a);codec2_weight_output[0]=codec2_weight_dc(&state);
        for(unsigned k=1;k<=128;++k){compact_complex positive,negative;codec2_weight_pair(&state,k,&positive,&negative);codec2_weight_output[k]=positive;codec2_weight_output[256-k]=negative;}
        codec2_weight_status=2;
        __asm__ __volatile__("" ::: "memory");
    }
}
