/* Direct paired-polynomial mailbox; optional compiled MUL-using ISR. */
#include <stdint.h>
#include "nb3_lsp_pair.h"
#include <avr/io.h>
volatile uint16_t pair_config[6];
#ifdef SPEEX_PAIR_IRQ_TEST
#include <avr/interrupt.h>
volatile uint16_t pair_irq_count,pair_accumulator;
ISR(TIMER2_COMPA_vect)
{
    uint8_t u=(uint8_t)pair_irq_count;
    pair_accumulator+=(uint16_t)(uint8_t)(u+37)*(uint8_t)(u+129);
    pair_irq_count++;
}
#endif
uint8_t pair_work[768];
volatile uint16_t pair_p,pair_q;
volatile int16_t pair_fp,pair_fq;
volatile uint8_t pair_number,pair_command,pair_status;
static SPEEX_NB3_STAGE void pair_selected(int32_t *p,int32_t *q,int16_t fp,int16_t fq,uint8_t n)
{
    if(n==2)speex_nb3_lsp_pair2(p,q,fp,fq);
    else if(n==3)speex_nb3_lsp_pair3(p,q,fp,fq);
    else speex_nb3_lsp_pair4(p,q,fp,fq);
}
static SPEEX_NB3_STAGE void pair_forced_c(int32_t *p,int32_t *q,int16_t fp,int16_t fq,uint8_t n)
{speex_nb3_lsp_pair_c(p,q,fp,fq,n);}
int main(void)
{
    pair_config[0]=_SFR_MEM_ADDR(SREG);
#ifdef SPEEX_PAIR_IRQ_TEST
    pair_config[1]=TIMER2_COMPA_vect_num*(_VECTORS_SIZE/(SPM_READY_vect_num+1))/2;
    pair_config[2]=_SFR_MEM_ADDR(TIFR2);pair_config[3]=_BV(OCF2A);
    pair_config[4]=_SFR_MEM_ADDR(TIMSK2);pair_config[5]=_BV(OCIE2A);
    TIMSK2=_BV(OCIE2A);sei();
#endif
    pair_p=(uint16_t)(uintptr_t)pair_work;pair_q=pair_p+384;pair_status=1;
    for(;;) {
        while(!pair_command){}
        int32_t *p=(int32_t *)(uintptr_t)pair_p,*q=(int32_t *)(uintptr_t)pair_q;
        if(pair_command==1)pair_selected(p,q,pair_fp,pair_fq,pair_number);
        else pair_forced_c(p,q,pair_fp,pair_fq,pair_number);
        pair_command=0;pair_status=2;
    }
}
