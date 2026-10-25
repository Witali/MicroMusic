#include <stdint.h>
#include "nb3_lsp_stage.h"
uint8_t stage_work[384];
volatile uint16_t stage_address;
volatile int16_t stage_f;
volatile uint8_t stage_number,stage_command,stage_status;
static SPEEX_NB3_STAGE void stage_selected(int32_t *p,int16_t f,uint8_t n)
{
    if(n==2)speex_nb3_lsp_stage2(p,f);
    else if(n==3)speex_nb3_lsp_stage3(p,f);else speex_nb3_lsp_stage4(p,f);
}
static SPEEX_NB3_STAGE void stage_forced_c(int32_t *p,int16_t f,uint8_t n)
{speex_nb3_lsp_stage_c(p,f,n);}
int main(void)
{
    stage_address=(uint16_t)(uintptr_t)stage_work;stage_status=1;
    for(;;){
        while(!stage_command){}
        int32_t *p=(int32_t *)(uintptr_t)stage_address;
        if(stage_command==1)stage_selected(p,stage_f,stage_number);else stage_forced_c(p,stage_f,stage_number);
        stage_command=0;stage_status=2;
    }
}
