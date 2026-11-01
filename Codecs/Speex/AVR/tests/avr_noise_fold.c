/* Scalar/vector arithmetic only; no C decoder execution. */
#include "wb_fold.h"
int16_t fold_cache[87],fold_output[42],fold_scratch[7];
volatile int32_t fold_gain;
volatile uint8_t fold_sub,fold_command,fold_status;
SPEEX_NB3_STAGE_O2 void fold_before(int16_t *out,const int16_t *cache,uint8_t sub,int32_t g)
{
    const uint8_t *classes=(const uint8_t *)cache+40*sub;
    for(uint8_t i=0;i<40;i++)out[i]=cache[80+classes[i]];
    speex_wb_fold40_avr(out,g);
}
int main(void)
{
    fold_status=1;
    for(;;)if(fold_command) {
        int16_t *out=fold_output+1,*scratch=fold_scratch+1;const int16_t *cache=fold_cache+1;
        if(fold_command==1)speex_wb_noise_fold40_avr(out,cache,fold_sub,fold_gain,scratch);
        else if(fold_command==2)speex_wb_noise_fold40_c(out,cache,fold_sub,fold_gain,scratch);
        else if(fold_command==3)fold_before(out,cache,fold_sub,fold_gain);
        else {
            for(uint8_t i=0;i<5;i++)out[i]=cache[80+i];
            if(fold_command==4)speex_wb_fold5_avr(out,fold_gain);
            else speex_wb_fold5_c(out,fold_gain);
        }
        fold_command=0;fold_status=2;
    }
}
