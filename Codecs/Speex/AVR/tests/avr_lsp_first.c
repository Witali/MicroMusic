#include <stdint.h>
#include <avr/io.h>
#include "nb3_lsp_first.h"
uint8_t first_work[384];
volatile uint16_t first_addresses[2];
volatile int16_t first_a,first_b;
volatile uint8_t first_command,first_status;
static SPEEX_NB3_STAGE void first_selected(int32_t *p,int16_t a,int16_t b)
{speex_nb3_lsp_first(p,a,b);}
static SPEEX_NB3_STAGE void first_forced_c(int32_t *p,int16_t a,int16_t b)
{speex_nb3_lsp_first_c(p,a,b);}
int main(void)
{
    first_addresses[0]=(uint16_t)(uintptr_t)first_work;first_addresses[1]=_SFR_MEM_ADDR(SREG);first_status=1;
    for(;;){
        while(!first_command){}
        int32_t *p=(int32_t *)(uintptr_t)first_addresses[0];
        if(first_command==1)first_selected(p,first_a,first_b);else first_forced_c(p,first_a,first_b);
        first_command=0;first_status=2;
    }
}
