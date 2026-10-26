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
static void attenuation(uint16_t coefficient,int16_t state){
    const int16_t actual=lpx4AttenuateQ14(coefficient,state);checkZero(actual);
    if(actual!=(product((int16_t)coefficient,state)>>14))math_error=12;
    ++math_cases;
}
static void pwm(int16_t sample,uint8_t gain){
    const uint8_t actual=lpx4PwmQ14(sample,gain);checkZero(actual);
    int32_t expected=128+((product(sample,gain)+8192)>>14);
    if(expected<0)expected=0;if(expected>255)expected=255;
    if(actual!=expected)math_error=13;
    ++math_cases;
}
__attribute__((noinline)) static uint16_t referenceLsf(int16_t p,int16_t c,uint8_t t){
    return (uint16_t)(((int32_t)p*(16-t)+(int32_t)c*t)>>2);
}
__attribute__((noinline)) static int16_t referenceClip15(int32_t value){
    return value<-32767?-32767:(value>32767?32767:(int16_t)value);
}
static void clip24(int32_t value){
    const int16_t actual=lpx4Clip15From24(value);checkZero(actual);
    if(actual!=referenceClip15(value))math_error=16;
    ++math_cases;
}
__attribute__((noinline)) static int32_t unsignedProduct(int8_t x,uint16_t y){return (int32_t)x*y;}
static void unsignedCase(int8_t x,uint16_t y){
    const int32_t actual=lpx4Mul8xU16(x,y);checkZero(actual);
    if(actual!=unsignedProduct(x,y))math_error=23;
    ++math_cases;
}
__attribute__((noinline)) static int32_t scaledRing(int32_t excitation,const int16_t* a,int16_t*& h){
    return lpx4SynthesisRingQ12<true>(excitation*16,a,h);
}
// Keep this second unrolled ASM kernel out of main: AVR-GCC underestimates
// assembler .rept size when choosing relative branches in a giant test body.
__attribute__((noinline)) static void ringCase(int32_t excitation,const int16_t* a,const int16_t* original,int32_t expected,uint8_t cursor){
    int16_t mirrored[20],beforeRing[20];
    for(uint8_t i=0;i<10;i++){
        const uint8_t slot=(cursor+9-i)%10;
        mirrored[slot]=mirrored[slot+10]=original[i];
    }
    for(uint8_t i=0;i<20;i++)beforeRing[i]=mirrored[i];
    int16_t* history=mirrored+cursor+10;
    const int32_t actual=lpx4SynthesisRingQ12(excitation,a,history);checkZero(actual);
    if(actual!=excitation-expected || history!=mirrored+cursor)math_error=19;
    for(uint8_t i=0;i<20;i++)if(mirrored[i]!=beforeRing[i])math_error=20;
    ++math_cases;
    history=mirrored+cursor+10;
    const int32_t scaled=scaledRing(excitation,a,history);checkZero(scaled);
    if(scaled!=excitation-expected || history!=mirrored+cursor)math_error=24;
    for(uint8_t i=0;i<20;i++)if(mirrored[i]!=beforeRing[i])math_error=25;
    ++math_cases;
}
template<uint8_t bits> __attribute__((noinline)) static void lpcCase(int16_t prev,int16_t cur,uint8_t t){
    const int16_t actual=lpx4LpcInterpolate(prev,cur,t,bits);checkZero(actual);
    const int32_t expected=prev+((int32_t)cur-prev)*t/(1L<<bits);
    if(actual!=expected)math_error=21;
    ++math_cases;
}
int main(){
#ifdef __AVR__
    TCCR1A=TCCR1B=0;OCR1A=1999;
    TIMSK1=_BV(OCIE1A);TCCR1B=_BV(WGM12)|_BV(CS10);sei();
#endif
    for(int8_t x=-32;x<32;x++)for(uint8_t gain=0;gain<32;gain++){
        const int8_t actual=lpx4PitchQ4(x,gain);checkZero(actual);
        if(actual!=((product(x,gain)+8)>>4))math_error=22;
        ++math_cases;
    }
    const int16_t anchors[]={-32768,-32767,-16384,-256,-1,0,1,255,16384,32766,32767};
    for(uint8_t p=0;p<11;p++)for(uint8_t c=0;c<11;c++){
        for(uint8_t t=0;t<=4;t++)lpcCase<2>(anchors[p],anchors[c],t);
        for(uint8_t t=0;t<=8;t++)lpcCase<3>(anchors[p],anchors[c],t);
        for(uint8_t t=0;t<=16;t++)lpcCase<4>(anchors[p],anchors[c],t);
    }
    uint16_t anchorBits=0;
    do{
        const int16_t p=(int16_t)anchorBits,c=(int16_t)(anchorBits*40503U+17U);
        lpcCase<2>(p,c,anchorBits%5);lpcCase<3>(p,c,anchorBits%9);lpcCase<4>(p,c,anchorBits%17);
    }while(++anchorBits);
    for(uint16_t i=0;i<20000;i++){
        const int16_t p=(int16_t)random32(),c=(int16_t)random32();
        lpcCase<2>(p,c,random32()%5);lpcCase<3>(p,c,random32()%9);lpcCase<4>(p,c,random32()%17);
    }
    const uint16_t coefficients[]={0,1,127,128,255,256,4095,8192,11469,16383,16384};
    for(uint8_t c=0;c<11;c++){
        uint16_t bits=0;
        do{attenuation(coefficients[c],(int16_t)bits);}while(++bits);
    }
    const int16_t states[]={-32768,-32767,-1,0,1,16383,32766,32767};
    for(uint16_t c=0;c<=16384;c++)for(uint8_t i=0;i<8;i++)attenuation(c,states[i]);
    for(uint8_t gain=120;gain<=136;gain++){
        uint16_t bits=0;
        do{pwm((int16_t)bits,gain);}while(++bits);
    }
    for(uint16_t gain=0;gain<256;gain++)for(uint8_t i=0;i<8;i++)pwm(states[i],gain);
    const int16_t lsfEdges[]={0,1,2,31,32,255,256,511,512,767,1022,1023};
    for(int16_t value=0;value<1024;value++)for(uint8_t i=0;i<12;i++)for(uint8_t t=0;t<=16;t++){
        if(lpx4LsfNorm10(value,lsfEdges[i],t)!=referenceLsf(value,lsfEdges[i],t))math_error=14;
        if(lpx4LsfNorm10(lsfEdges[i],value,t)!=referenceLsf(lsfEdges[i],value,t))math_error=14;
        math_cases+=2;
    }
    for(int16_t x=-128;x<128;x++)for(uint16_t y=0;y<4096;y++){
        const int32_t actual=lpx4Excitation((int8_t)x,y);checkZero(actual);
        if(actual!=product(x,y))math_error=8;
        ++math_cases;
    }
    const int16_t edges[]={-32768,-32767,-16385,-16384,-1,0,1,4095,16384,32766,32767};
    for(uint8_t i=0;i<11;i++){
        uint16_t bits=0;
        do{
            const int16_t actual=lpx4AddClip15(edges[i],(int16_t)bits);checkZero(actual);
            if(actual!=referenceClip15((int32_t)edges[i]+(int16_t)bits))math_error=17;
            ++math_cases;
        }while(++bits);
    }
    for(int32_t v=-65536;v<65536;v++)clip24(v);
    const uint16_t lowEdges[]={0,1,32767,32768,32769,65535};
    for(int16_t high=-128;high<128;high++)for(uint8_t j=0;j<6;j++)clip24((int32_t)high*65536L+lowEdges[j]);
    uint16_t bits=0;
    do{
        const int16_t value=(int16_t)bits,actual=lpx4ClipQ14(value);checkZero(actual);
        const int16_t expected=value<-16384?-16384:(value>16384?16384:value);
        if(actual!=expected)math_error=18;
        ++math_cases;
    }while(++bits);
    const int8_t byteEdges[]={-128,-127,-64,-1,0,1,64,127};
    for(uint8_t i=0;i<8;i++){
        uint16_t bits=0;
        do{
            const int32_t actual=lpx4Mul8x16(byteEdges[i],(int16_t)bits);checkZero(actual);
            if(actual!=product(byteEdges[i],(int16_t)bits))math_error=15;
            ++math_cases;
            unsignedCase(byteEdges[i],bits);
        }while(++bits);
    }
    for(int16_t x=-128;x<128;x++)for(uint8_t i=0;i<11;i++){
        const int32_t actual=lpx4Mul8x16((int8_t)x,edges[i]);checkZero(actual);
        if(actual!=product(x,edges[i]))math_error=15;
        ++math_cases;
        unsignedCase((int8_t)x,(uint16_t)edges[i]);
    }
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
        clip24(synthesized);
        if(h[0]!=original[0])math_error=10;
        for(uint8_t i=1;i<10;i++)if(h[i]!=original[i-1])math_error=11;
        ++math_cases;
        ringCase(excitation,a,original,expected,n%10);
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
