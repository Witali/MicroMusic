#include <stdint.h>
#include <avr/io.h>
#include "nb3_lsp_angle.h"
int16_t reference_lsp_angle(int16_t);
volatile int16_t angle_input,angle_result;
volatile uint8_t angle_command,angle_status;
volatile uint16_t angle_config[6];
#ifdef SPEEX_ANGLE_IRQ_TEST
#include <avr/interrupt.h>
volatile uint16_t angle_irq_count,angle_accumulator;
ISR(TIMER2_COMPA_vect)
{
    uint8_t u=(uint8_t)angle_irq_count;
    angle_accumulator+=(uint16_t)(uint8_t)(u+37)*(uint8_t)(u+129);angle_irq_count++;
}
#endif
static SPEEX_NB3_STAGE int16_t angle_selected(int16_t x){return speex_nb3_lsp_angle(x);}
static SPEEX_NB3_STAGE int16_t angle_forced_c(int16_t x){return speex_nb3_lsp_angle_c(x);}
int main(void)
{
    angle_config[0]=_SFR_MEM_ADDR(SREG);
#ifdef SPEEX_ANGLE_IRQ_TEST
    angle_config[1]=TIMER2_COMPA_vect_num*(_VECTORS_SIZE/(SPM_READY_vect_num+1))/2;
    angle_config[2]=_SFR_MEM_ADDR(TIFR2);angle_config[3]=_BV(OCF2A);
    angle_config[4]=_SFR_MEM_ADDR(TIMSK2);angle_config[5]=_BV(OCIE2A);
    TIMSK2=_BV(OCIE2A);sei();
#endif
    angle_status=1;
    for(;;) {
        while(!angle_command){}
        if(angle_command==1)angle_result=angle_selected(angle_input);
        else if(angle_command==2)angle_result=angle_forced_c(angle_input);
        else angle_result=reference_lsp_angle(angle_input);
        angle_command=0;angle_status=2;
    }
}
