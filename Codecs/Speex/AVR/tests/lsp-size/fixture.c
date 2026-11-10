/* Isolated order-eight scalar reference, selected backend, ABI and IRQ. */
#include <stdint.h>
#include <avr/io.h>
#include <avr/interrupt.h>
#include "nb3_lsp_finish.h"
void speex_avr_lsp_finish8(const int32_t *,const int32_t *,int16_t *);
uint8_t finish_work[1152];
volatile uint16_t finish_addresses[3],finish_device[3],finish_irq_sum;
volatile uint32_t finish_irq_count;
volatile uint8_t finish_command,finish_status;
ISR(TIMER2_COMPA_vect) {
    uint8_t x=(uint8_t)finish_irq_count;
    finish_irq_sum+=(uint16_t)(uint8_t)(x+37)*(uint8_t)(x+129);++finish_irq_count;
}
SPEEX_NB3_STAGE void finish8_selected(const int32_t *p,const int32_t *q,int16_t *a)
{speex_nb3_lsp_finish8(p,q,a);}
SPEEX_NB3_STAGE void finish8_paired_c(const int32_t *p,const int32_t *q,int16_t *a)
{speex_nb3_lsp_finish8_c(p,q,a);}
#define SEQUENTIAL_BODY \
    int32_t previous_p=0,previous_q=0; \
    for(int j=1;j<=8;j++) { \
        int index=j<=4?j:8-j; \
        int32_t value=(p[index]+previous_p+q[index]-previous_q+128)>>8; \
        previous_p=p[index];previous_q=q[index]; \
        if(value< -32767)value=-32767;if(value>32767)value=32767;a[j-1]=(int16_t)value; \
    }
SPEEX_NB3_NOINLINE __attribute__((noclone,optimize("Os")))
void finish8_sequential_os(const int32_t *restrict p,const int32_t *restrict q,int16_t *restrict a)
{SEQUENTIAL_BODY}
SPEEX_NB3_STAGE void finish8_sequential_o3(const int32_t *restrict p,const int32_t *restrict q,int16_t *restrict a)
{SEQUENTIAL_BODY}
int main(void) {
    finish_device[0]=_SFR_MEM_ADDR(TCCR2B);finish_device[1]=_BV(CS21);
    finish_device[2]=TIMER2_COMPA_vect_num*(_VECTORS_SIZE/(SPM_READY_vect_num+1))/2;
    OCR2A=63;TCCR2A=_BV(WGM21);TIMSK2=_BV(OCIE2A);
    finish_addresses[0]=(uint16_t)(uintptr_t)finish_work;finish_status=1;sei();
    for(;;)if(finish_command) {
        const int32_t *p=(const int32_t *)(uintptr_t)finish_addresses[0];
        const int32_t *q=(const int32_t *)(uintptr_t)finish_addresses[1];
        int16_t *a=(int16_t *)(uintptr_t)finish_addresses[2];
        if(finish_command==1)finish8_selected(p,q,a);
        else if(finish_command==2)finish8_paired_c(p,q,a);
        else if(finish_command==3)finish8_sequential_os(p,q,a);
        else if(finish_command==4)finish8_sequential_o3(p,q,a);
        else speex_avr_lsp_finish8(p,q,a);
        finish_command=0;finish_status=2;
    }
}
