/* Both orders, selectable/forced C, optional real compiled MUL-using ISR. */
#include <stdint.h>
#include <avr/io.h>
#include "wb_iir.h"
void speex_test_iir10_c(const int16_t *,const int16_t *,int16_t *,int32_t *);
#if SPEEX_NB3_USE_AVR_ASM
void speex_avr_iir40(const int16_t *,const int16_t *,int16_t *,int32_t *);
#endif
uint8_t iir_work[768];
volatile uint16_t iir_x,iir_den,iir_out,iir_state,iir_config[6];
volatile uint8_t iir_order,iir_command,iir_status;
#ifdef SPEEX_IIR_IRQ_TEST
#include <avr/interrupt.h>
volatile uint16_t iir_irq_count,iir_accumulator;
ISR(TIMER2_COMPA_vect)
{
    uint8_t u=(uint8_t)iir_irq_count;
    iir_accumulator+=(uint16_t)(uint8_t)(u+37)*(uint8_t)(u+129);++iir_irq_count;
}
#endif
int main(void)
{
    iir_x=(uint16_t)(uintptr_t)(iir_work+4);iir_den=(uint16_t)(uintptr_t)(iir_work+284);
    iir_out=(uint16_t)(uintptr_t)(iir_work+132);iir_state=(uint16_t)(uintptr_t)(iir_work+352);
    iir_config[0]=_SFR_MEM_ADDR(SREG);
#ifdef SPEEX_IIR_IRQ_TEST
    iir_config[1]=TIMER2_COMPA_vect_num*(_VECTORS_SIZE/(SPM_READY_vect_num+1))/2;
    iir_config[2]=_SFR_MEM_ADDR(TIFR2);iir_config[3]=_BV(OCF2A);
    iir_config[4]=_SFR_MEM_ADDR(TIMSK2);iir_config[5]=_BV(OCIE2A);
    TIMSK2=_BV(OCIE2A);sei();
#endif
    iir_status=1;
    for(;;) {
        while(!iir_command){}
        const int16_t *x=(const int16_t *)(uintptr_t)iir_x,*den=(const int16_t *)(uintptr_t)iir_den;
        int16_t *out=(int16_t *)(uintptr_t)iir_out;int32_t *state=(int32_t *)(uintptr_t)iir_state;
        if(iir_order==8) {
            if(iir_command==1)speex_wb_iir40(x,den,out,state);
            else speex_wb_iir40_c(x,den,out,state);
        } else {
#if SPEEX_NB3_USE_AVR_ASM
            if(iir_command==1)speex_avr_iir40(x,den,out,state);
            else
#endif
            speex_test_iir10_c(x,den,out,state);
        }
        iir_command=0;iir_status=2;
    }
}
