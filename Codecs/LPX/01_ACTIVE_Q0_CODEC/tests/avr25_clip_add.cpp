// Independent integral-Q4 clipping and full signed16 addition oracles.
#include <avr/interrupt.h>
#include <stdint.h>
#include "Lpx4Math.h"

extern "C" {
volatile uint32_t math_cases,math_irqs;
volatile uint8_t math_done,math_error,math_zero_error,math_backend;
}
ISR(TIMER1_OVF_vect) { ++math_irqs; }

static int16_t clamp15(int32_t value){
    return value<-32767?-32767:value>32767?32767:(int16_t)value;
}
static void checkZero(){
    uint8_t value;
    __asm__ volatile("mov %0,__zero_reg__":"=r"(value));
    if(value)math_zero_error=1;
}
static void clip(int32_t units){
    // Synthesis removes each product's fractional nibble before summation.
    const int16_t actual=lpx4ClipSynthesisQ4(units*16);
    checkZero();
    if(actual!=clamp15(units))math_error=1;
    ++math_cases;
}
static void add(int16_t a,int16_t b){
    const int16_t actual=lpx4AddClip15<true>(a,b);
    checkZero();
    if(actual!=clamp15((int32_t)a+b))math_error=1;
    ++math_cases;
}
int main(){
    math_backend=LPX4_USE_AVR_NOMUL_ASM;
    TIMSK1=_BV(TOIE1);
    TCCR1B=_BV(CS10);
    sei();
    for(int32_t units=-524288;units<524288 && !math_error;++units)clip(units);
    const int32_t limits[]={-8388608,-8388607,-1048577,-1048576,-1048575,-65537,-65536,-65535,
        -32769,-32768,-32767,-32766,-1,0,1,32766,32767,32768,32769,65535,65536,65537,
        1048575,1048576,1048577,8388606,8388607};
    for(int32_t units:limits)if(!math_error)clip(units);
    const int16_t boundaries[]={-32768,-32767,-32766,-16384,-4096,-255,-2,-1,0,1,2,255,4096,16384,32765,32766,32767};
    for(int16_t a:boundaries)for(uint32_t b=0;b<65536 && !math_error;++b)add(a,b);
    uint32_t random=53;
    for(uint32_t i=0;i<131072 && !math_error;++i){
        random=random*1664525UL+1013904223UL;
        const int32_t units=(int32_t)(random<<8)>>8;
        clip(units);
        random=random*1664525UL+1013904223UL;
        add(random>>16,random);
    }
    math_done=1;
    for(;;){}
}
