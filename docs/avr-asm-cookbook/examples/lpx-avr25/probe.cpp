#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/pgmspace.h>
#include "avr25_math.h"
#include "vectors.h"
extern "C" {
volatile uint8_t probe_done,probe_irq_enable,probe_error,probe_op,probe_zero,probe_ready;
volatile uint16_t probe_index,probe_irqs;
volatile int32_t probe_result;
}
ISR(TIMER1_OVF_vect){++probe_irqs;}
static void publish(uint8_t op,uint16_t index,int32_t result){
    probe_op=op;probe_index=index;probe_result=result;
    uint8_t zero;__asm__ volatile("mov %0,__zero_reg__":"=r"(zero));
    probe_zero=zero;if(zero)probe_error=1;
    probe_ready^=1;
}
int main(){
    if(probe_irq_enable){
        TCCR1A=_BV(WGM10);TCCR1B=_BV(WGM12)|_BV(CS10);
        TIMSK1=_BV(TOIE1);sei();
    }
    for(uint16_t i=0;i<PRODUCT_COUNT;++i){
        const int16_t x=(int16_t)pgm_read_word(&product_inputs[i][0]);
        const int16_t y=(int16_t)pgm_read_word(&product_inputs[i][1]);
        publish(0,i,proto_mul(x,y));
    }
    for(uint16_t i=0;i<SHIFT_COUNT;++i){
        const int32_t value=(int32_t)pgm_read_dword(&shift_inputs[i]);
        publish(1,i,proto_shift12(value));publish(2,i,proto_shift14(value));
    }
    cli();probe_done=1;for(;;){}
}
