/* Isolated scalar arithmetic/ABI fixture, never a C decoder runtime. */
#include <avr/io.h>
#include <avr/interrupt.h>
#include "wb_gain_div.h"
/* Direct control remains available when selected arithmetic is C. */
#if !SPEEX_NB3_USE_AVR_ASM
int16_t speex_wb_ratio_div_avr(int32_t,int32_t);
#endif
volatile int32_t ratio_low,ratio_high;
volatile int16_t ratio_result;
volatile uint8_t ratio_command,ratio_status;
volatile uint32_t ratio_irq_count;
volatile uint16_t ratio_irq_sum,ratio_device[3];
ISR(TIMER2_COMPA_vect)
{
    uint8_t x=(uint8_t)ratio_irq_count;
    ratio_irq_sum+=(uint16_t)(uint8_t)(x+37)*(uint8_t)(x+129);
    ++ratio_irq_count;
}
SPEEX_NB3_STAGE int16_t ratio_reference(int32_t low,int32_t high)
{return speex_wb_ratio_div_c(low,high);}
SPEEX_NB3_STAGE int16_t ratio_selected(int32_t low,int32_t high)
{return speex_wb_ratio_div(low,high);}
int main(void)
{
    /* Timer stays stopped unless the verifier starts its clock. */
    ratio_device[0]=_SFR_MEM_ADDR(TCCR2B);
    ratio_device[1]=_BV(CS21);
    ratio_device[2]=TIMER2_COMPA_vect_num*(_VECTORS_SIZE/(SPM_READY_vect_num+1))/2;
    OCR2A=63;TCCR2A=_BV(WGM21);TIMSK2=_BV(OCIE2A);
    ratio_status=1;sei();
    for(;;)if(ratio_command) {
        int32_t a=ratio_low,d=ratio_high;
        if(ratio_command==1)
            ratio_result=speex_wb_ratio_div_avr(a*128+((int16_t)d>>1),d);
        else if(ratio_command==2)ratio_result=ratio_reference(a,d);
        else ratio_result=ratio_selected(a,d);
        ratio_command=0;ratio_status=2;
    }
}
