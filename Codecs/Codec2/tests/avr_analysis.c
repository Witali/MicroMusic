#include "fixed_analysis.h"
#include <stdint.h>
volatile float codec2_analysis_input[11];
compact_transform codec2_analysis_output;
volatile uint8_t codec2_analysis_command,codec2_analysis_status;
int main(void){
    codec2_analysis_status=1;
    for(;;)if(codec2_analysis_command){
        float a[11];codec2_analysis_command=0;
        for(unsigned i=0;i<11;++i)a[i]=codec2_analysis_input[i];
        codec2_analysis_forward(&codec2_analysis_output,a);codec2_analysis_status=2;
        __asm__ __volatile__("" ::: "memory");
    }
}
