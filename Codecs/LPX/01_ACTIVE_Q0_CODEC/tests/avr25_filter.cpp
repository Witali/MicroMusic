// Arithmetic-only probe. Test inputs are supplied externally; no audio data.
#include <stdint.h>
#include "Lpx4Math.h"

#if defined(__AVR__)
#include <avr/io.h>
#include <avr/interrupt.h>
extern "C" {
volatile uint8_t filter_ready,filter_backend;
volatile uint16_t filter_irqs;
__attribute__((noinline,used)) uint16_t filter_prepare(uint16_t coefficient){
#if LPX4_USE_AVR_NOMUL_ASM
    return lpx4PrepareAttenuationQ14(coefficient);
#else
    return coefficient;
#endif
}
__attribute__((noinline,used)) int16_t filter_product(int16_t state,uint16_t coefficient){
#if LPX4_USE_AVR_NOMUL_ASM
    return lpx4PreparedAttenuationQ14(state,coefficient);
#else
    return lpx4AttenuateQ14(coefficient,state);
#endif
}
}
ISR(TIMER1_OVF_vect){++filter_irqs;}
int main(){
    filter_backend=LPX4_USE_AVR_NOMUL_ASM;
    TIMSK1=_BV(TOIE1);TCCR1A=_BV(WGM10);TCCR1B=_BV(WGM12)|_BV(CS10);
    sei();filter_ready=1;for(;;){}
}
#else
#include <cstdio>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
static bool check(uint16_t coefficient,int32_t state){
    const int16_t actual=lpx4AttenuateQ14(coefficient,(int16_t)state);
    const int32_t product=(int32_t)coefficient*state;
    // Independent explicit floor division, without relying on signed shifts.
    const int32_t expected=product>=0?product/16384:-((-product+16383)/16384);
    if(actual!=expected)return false;
    const uint16_t word=(uint16_t)actual;putchar(word&255);putchar(word>>8);
    return true;
}
int main(){
#ifdef _WIN32
    if(_setmode(_fileno(stdout),_O_BINARY)==-1)return 1;
#endif
    const uint16_t coefficients[]={0,1,63,64,65,7800,8192,13094,13926,11468,11469,16383,16384};
    for(uint16_t coefficient:coefficients)
        for(int32_t state=-32768;state<=32767;state++)if(!check(coefficient,state))return 2;
    const int16_t states[]={-32768,-16384,-1,0,1,16384,32767};
    for(uint16_t coefficient=0;coefficient<=16384;coefficient++)
        for(int16_t state:states)if(!check(coefficient,state))return 3;
    return ferror(stdout)?4:0;
}
#endif
