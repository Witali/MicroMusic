// Compare the complete filter result and state before PWM clipping.
#include <avr/interrupt.h>
#include <stdint.h>
#include "Lpx4Math.h"

extern "C" {
volatile uint32_t math_cases,math_irqs;
volatile uint8_t math_done,math_error,math_zero_error,math_backend;
}
ISR(TIMER1_OVF_vect) { ++math_irqs; }

static uint8_t state[16];
static int16_t clamp15(int32_t value){
    return value<-32767?-32767:value>32767?32767:(int16_t)value;
}
static int16_t clamp14(int16_t value){
    return value<-16384?-16384:value>16384?16384:value;
}
static int16_t product(uint16_t coefficient,int16_t value){
    const int32_t p=(int32_t)coefficient*value;
    return p>=0?p/16384:-((-p+16383)/16384);
}
static void put(uint8_t offset,uint16_t value){
    state[offset]=(uint8_t)value;
    state[offset+1]=(uint8_t)(value>>8);
}
static void check(uint16_t pre,uint16_t bright,int16_t previous,int16_t predicted){
    for(uint8_t i=0;i<sizeof state;++i)state[i]=i*17+3;
    put(0,pre);
    put(2,bright);
    put(10,previous);
    const int16_t output=lpx4PostfilterPair<10>(predicted,state);
    uint8_t zero;
    __asm__ volatile("mov %0,__zero_reg__" : "=r"(zero));
    if(zero)math_zero_error=1;
    const int16_t deemph=pre?clamp15((int32_t)predicted+product(pre,previous)):predicted;
    const int16_t expected=clamp14(deemph)-product(bright,clamp14(previous));
    const int16_t stored=(int16_t)((uint16_t)state[10]|((uint16_t)state[11]<<8));
    if(output!=expected || stored!=deemph)math_error=1;
    for(uint8_t i=0;i<sizeof state;++i){
        const uint8_t expectedByte=i<2?(uint8_t)(pre>>(8*i)):i<4?(uint8_t)(bright>>(8*(i-2))):
            i==10?(uint8_t)deemph:i==11?(uint8_t)((uint16_t)deemph>>8):i*17+3;
        if(state[i]!=expectedByte)math_error=1;
    }
    ++math_cases;
}

int main(){
    math_backend=LPX4_USE_AVR_ASM;
    TIMSK1=_BV(TOIE1);
    TCCR1B=_BV(CS10);
    sei();
    const uint16_t pres[]={0,1,2,63,64,65,255,256,257,8191,8192,8193,11469,16382,16383,16384};
    const uint16_t brights[]={0,1,2,63,64,65,255,256,257,4095,4096,4097,8191,8192,8193,11468,11469};
    const int16_t values[]={-32768,-32767,-32766,-16385,-16384,-16383,-1,0,1,16383,16384,16385,32765,32766,32767};
    const int16_t endpoints[]={-32768,0,32767};
    for(uint16_t pre:pres)for(uint16_t bright:brights)
        for(int16_t old:values)for(int16_t prediction:values){
            if(math_error)goto done;
            check(pre,bright,old,prediction);
        }
    for(uint8_t mode=0;mode<8 && !math_error;++mode)
        for(int16_t previous:endpoints)
            for(uint32_t predicted=0;predicted<65536 && !math_error;++predicted)
                check(mode&1?16384:mode&2?16383:0,mode&4?11469:0,previous,predicted);
    {
        uint16_t random=53;
        for(uint32_t i=0;i<131072 && !math_error;++i){
            random=random*421+19;
            const uint16_t pre=(uint32_t)random*16385>>16;
            random=random*421+19;
            const uint16_t bright=(uint32_t)random*11470>>16;
            random=random*421+19;
            const int16_t previous=random;
            random=random*421+19;
            check(pre,bright,previous,random);
        }
    }
done:
    math_done=1;
    for(;;){}
}
