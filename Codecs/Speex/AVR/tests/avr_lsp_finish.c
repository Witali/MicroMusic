/* Direct arithmetic/ABI mailbox; no hardware or original-oracle workspace. */
#include <stdint.h>
#include "nb3_lsp_finish.h"
uint8_t finish_work[1152];
volatile uint16_t finish_addresses[3];
volatile uint8_t finish_command,finish_status;
static SPEEX_NB3_STAGE void finish_selected(const int32_t *p,const int32_t *q,int16_t *a)
{speex_nb3_lsp_finish10(p,q,a);}
static SPEEX_NB3_STAGE void finish_forced_c(const int32_t *p,const int32_t *q,int16_t *a)
{speex_nb3_lsp_finish10_c(p,q,a);}
int main(void)
{
    finish_addresses[0]=(uint16_t)(uintptr_t)finish_work;finish_status=1;
    for(;;){
        while(!finish_command){}
        const int32_t *p=(const int32_t *)(uintptr_t)finish_addresses[0];
        const int32_t *q=(const int32_t *)(uintptr_t)finish_addresses[1];
        int16_t *a=(int16_t *)(uintptr_t)finish_addresses[2];
        if(finish_command==1)finish_selected(p,q,a);else finish_forced_c(p,q,a);
        finish_command=0;finish_status=2;
    }
}
