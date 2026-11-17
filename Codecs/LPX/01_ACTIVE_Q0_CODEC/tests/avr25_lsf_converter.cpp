
#include <avr/io.h>
#include <avr/interrupt.h>
#define private public
#include "Lpx4HybridCore.h"
#undef private
#include "Lpx4HybridCore.cpp"
static Lpx4HybridCore decoder;
extern "C" {
volatile uint8_t probe_ready,probe_cursor,probe_profile,probe_t,probe_error;
volatile uint16_t probe_irqs;
struct Output {uint8_t before;int16_t coefficients[10];uint8_t after;};
Output probe_result;
__attribute__((noinline,used)) void probe_case(){
    const uint8_t cursor=probe_cursor;
    const uint8_t profile=probe_profile;
    const uint8_t stride=(profile&2)?5:2;
    decoder.speechProfile_=profile;
    decoder.staticSpectrum_=false;
    decoder.ringCursor_=cursor;
    uint8_t* old=reinterpret_cast<uint8_t*>(decoder.lpcAnchors_+10);
    for(uint8_t i=0;i<10;++i){
        old[i]=1+i*stride;
        decoder.cur_[i]=2+i*stride;
    }
    uint8_t i=0;
    do{decoder.ringQ_[i]=(int8_t)((i*13u&63)-32);++i;}while(i);
    probe_result.before=0x35;probe_result.after=0xa6;probe_error=0;
    decoder.convertLsfAt(probe_t,probe_result.coefficients);
    for(uint8_t lag=1;lag<=145;++lag){
        const uint8_t at=cursor-lag;
        if(decoder.ringQ_[at]!=(int8_t)((at*13u&63)-32))probe_error=1;
    }
    if(probe_result.before!=0x35||probe_result.after!=0xa6)probe_error=2;
    if(decoder.ringCursor_!=cursor)probe_error=3;
    for(uint8_t i=0;i<10;++i)
        if(decoder.cur_[i]!=2+i*stride||old[i]!=1+i*stride)probe_error=4;
}
}
ISR(TIMER1_OVF_vect){++probe_irqs;}
int main(){
    TIMSK1=_BV(TOIE1);TCCR1A=_BV(WGM10);TCCR1B=_BV(WGM12)|_BV(CS10);
    sei();probe_ready=1;for(;;){}
}
