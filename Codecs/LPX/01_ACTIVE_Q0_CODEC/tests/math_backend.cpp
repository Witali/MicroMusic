// Independent full-range arithmetic oracle, compiled for host and real AVR.
#include <stdint.h>
#include "Lpx4Math.h"
#ifdef __AVR__
#include <avr/io.h>
#include <avr/interrupt.h>
#else
#include <stdio.h>
#endif
extern "C" {
volatile uint8_t math_done, math_error, math_zero_error;
volatile uint32_t math_cases, math_irqs;
volatile const uint8_t math_backend = LPX4_USE_AVR_ASM;
}
#ifdef __AVR__
ISR(TIMER1_COMPA_vect){ ++math_irqs; }
#endif
static uint32_t random_state=0x72e9a431UL;
static uint32_t random32(){
    uint32_t x=random_state;
    x^=x<<13;x^=x>>17;x^=x<<5;
    return random_state=x;
}
static inline void checkZero(int32_t dependency){
#ifdef __AVR__
    uint8_t value;
    __asm__ volatile("mov %0,r1":"=r"(value):"r"(dependency):"memory");
    if(value)math_zero_error=1;
#endif
}
__attribute__((noinline)) static int32_t product(int16_t x,int16_t y){ return (int32_t)x*y; }
__attribute__((noinline)) static int32_t referenceDot(const int16_t* a,const int16_t* h){
    int32_t result=0;
    for(uint8_t i=0;i<10;i++)result+=product(a[i],h[i])>>12;
    return result;
}
static void scalar(int16_t x,int16_t y,int32_t v){
    const int32_t expected=product(x,y);
    int32_t actual=lpx4Mul16(x,y);checkZero(actual);
    if(actual!=expected)math_error=1;
    actual=lpx4MulQ14(x,y);checkZero(actual);
    if(actual!=(expected>>14))math_error=2;
    actual=lpx4Shift12(v);checkZero(actual);
    if(actual!=(v>>12))math_error=3;
    actual=lpx4Shift14(v);checkZero(actual);
    if(actual!=(v>>14))math_error=4;
    ++math_cases;
}
int main(){
#ifdef __AVR__
    TCCR1A=TCCR1B=0;OCR1A=1999;
    TIMSK1=_BV(OCIE1A);TCCR1B=_BV(WGM12)|_BV(CS10);sei();
#endif
    for(int16_t x=-128;x<128;x++)for(uint16_t y=0;y<4096;y++){
        const int32_t actual=lpx4Excitation((int8_t)x,y);checkZero(actual);
        if(actual!=product(x,y))math_error=8;
        ++math_cases;
    }
    const int16_t edges[]={-32768,-32767,-16385,-16384,-1,0,1,4095,16384,32766,32767};
    for(uint8_t i=0;i<11;i++)for(uint8_t j=0;j<11;j++)
        scalar(edges[i],edges[j],(int32_t)((uint32_t)(uint16_t)edges[i]<<16 | (uint16_t)edges[j]));
    for(uint32_t n=0;n<16384 && !math_error && !math_zero_error;n++){
        scalar((int16_t)random32(),(int16_t)random32(),(int32_t)random32());
        int16_t a[10],h[10],original[10];
        for(uint8_t i=0;i<10;i++){
            a[i]=(int16_t)random32();h[i]=original[i]=(int16_t)random32();
            // Include worst-case sums and all sign/byte boundaries.
            if(n<121){a[i]=edges[n/11];h[i]=original[i]=edges[n%11];}
        }
        const int32_t expected=referenceDot(a,h);
        const int32_t actual=lpx4DotQ12(a,h);checkZero(actual);
        if(actual!=expected)math_error=5;
        if(h[0]!=original[0])math_error=6;
        for(uint8_t i=1;i<10;i++)if(h[i]!=original[i-1])math_error=7;
        ++math_cases;
        for(uint8_t i=0;i<10;i++)h[i]=original[i];
        const int32_t excitation=n%3==0 ? -524288L : n%3==1 ? 524287L :
            (int32_t)(random32()&1048575UL)-524288L;
        const int32_t synthesized=lpx4SynthesisQ12(excitation,a,h);checkZero(synthesized);
        if(synthesized!=excitation-expected)math_error=9;
        if(h[0]!=original[0])math_error=10;
        for(uint8_t i=1;i<10;i++)if(h[i]!=original[i-1])math_error=11;
        ++math_cases;
    }
#ifdef __AVR__
    cli();TCCR1B=0;
#else
    printf("{\"cases\":%lu,\"backend\":%u,\"error\":%u,\"zero_error\":%u}\n",
        (unsigned long)math_cases,math_backend,math_error,math_zero_error);
#endif
    math_done=1;
#ifdef __AVR__
    for(;;){}
#else
    return math_error || math_zero_error;
#endif
}
