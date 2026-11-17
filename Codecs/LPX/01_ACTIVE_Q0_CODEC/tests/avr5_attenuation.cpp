// Exercise carries in the bounded signed16 by unsigned Q14 product.
#include <avr/interrupt.h>
#include <stdint.h>
#include "Lpx4Math.h"

extern "C" {
volatile uint32_t math_cases, math_irqs;
volatile uint8_t math_done, math_error, math_zero_error, math_backend;
}
ISR(TIMER1_OVF_vect) { ++math_irqs; }

static void check(uint16_t coefficient,int16_t state){
    const int16_t actual=lpx4AttenuateQ14(coefficient,state);
    const int32_t product=(int32_t)coefficient*state;
    const int16_t expected=product>=0?product/16384:-((-product+16383)/16384);
    uint8_t zero;
    __asm__ volatile("mov %0,__zero_reg__" : "=r"(zero));
    if(zero)math_zero_error=1;
    if(actual!=expected)math_error=1;
    ++math_cases;
}

int main(){
    math_backend=LPX4_USE_AVR_ASM;
    TIMSK1=_BV(TOIE1);
    TCCR1B=_BV(CS10);
    sei();
    const uint16_t boundary[]={0,1,2,3,63,64,65,127,128,129,254,255,256,257,
        511,512,513,1023,1024,1025,4095,4096,4097,8191,8192,8193,11468,11469,
        11470,12287,12288,12289,16382,16383,16384};
    for(uint16_t coefficient:boundary)
        for(uint32_t state=0;state<65536 && !math_error;++state)
            check(coefficient,(int16_t)state);
    uint16_t state=53;
    for(uint32_t i=0;i<131072 && !math_error;++i){
        state=state*421+19;
        const uint16_t coefficient=(uint32_t)state*16385>>16;
        state=state*421+19;
        check(coefficient,state);
    }
    math_done=1;
    for(;;){}
}
