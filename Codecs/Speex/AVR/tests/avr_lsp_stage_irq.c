/* Synthetic instruction-boundary IRQ proof; actual timer playback is tested
 * separately. All peripheral addresses/vector spacing come from avr/io.h. */
#include <stdint.h>
#include <avr/io.h>
#include <avr/interrupt.h>
#include "nb3_lsp_stage.h"
uint8_t irq_stage_work[384];
volatile uint16_t irq_stage_address,irq_stage_count,irq_stage_accumulator;
volatile int16_t irq_stage_f;
volatile uint8_t irq_stage_number,irq_stage_command,irq_stage_status;
volatile uint16_t irq_stage_config[6];
ISR(TIMER2_COMPA_vect)
{
    uint8_t u=(uint8_t)irq_stage_count;
    uint16_t product=(uint16_t)(uint8_t)(u+37)*(uint8_t)(u+129);
    irq_stage_accumulator+=product;irq_stage_count++;
}
static SPEEX_NB3_STAGE void irq_stage_selected(int32_t *p,int16_t f,uint8_t n)
{
    if(n==2)speex_nb3_lsp_stage2(p,f);
    else if(n==3)speex_nb3_lsp_stage3(p,f);else speex_nb3_lsp_stage4(p,f);
}
static SPEEX_NB3_STAGE void irq_stage_forced_c(int32_t *p,int16_t f,uint8_t n)
{speex_nb3_lsp_stage_c(p,f,n);}
int main(void)
{
    irq_stage_config[0]=_SFR_MEM_ADDR(SREG);
    /* SPM_READY is this pinned ATmega328P header's final vector. Derive
     * spacing from its complete table size, then convert bytes to words. */
    irq_stage_config[1]=TIMER2_COMPA_vect_num*(_VECTORS_SIZE/(SPM_READY_vect_num+1))/2;
    irq_stage_config[2]=_SFR_MEM_ADDR(TIFR2);irq_stage_config[3]=_BV(OCF2A);
    irq_stage_config[4]=_SFR_MEM_ADDR(TIMSK2);irq_stage_config[5]=_BV(OCIE2A);
    TIMSK2=_BV(OCIE2A); /* host raises the flag; timer clock stays disabled */
    irq_stage_address=(uint16_t)(uintptr_t)irq_stage_work;irq_stage_status=1;sei();
    for(;;){
        while(!irq_stage_command){}
        int32_t *p=(int32_t *)(uintptr_t)irq_stage_address;
        if(irq_stage_command==1)irq_stage_selected(p,irq_stage_f,irq_stage_number);
        else irq_stage_forced_c(p,irq_stage_f,irq_stage_number);
        irq_stage_command=0;irq_stage_status=2;
    }
}
