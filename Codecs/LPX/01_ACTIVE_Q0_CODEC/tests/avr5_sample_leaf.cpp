#include <avr/interrupt.h>
#define private public
#include "Lpx4HybridCore.cpp"
#undef private

extern "C" {
volatile uint32_t math_cases, math_irqs;
volatile uint8_t math_done, math_error, math_zero_error, math_backend;
}
ISR(TIMER1_OVF_vect) { ++math_irqs; }

static int8_t expected(int8_t x,uint8_t gain,int8_t pulse){
    const int16_t raw=((int16_t)x*gain+8)>>4;
    const int16_t withPulse=raw+pulse;
    return withPulse<-32?-32:withPulse>31?31:(int8_t)withPulse;
}

int main(){
    math_backend=LPX4_USE_AVR_ASM;
    TIMSK1=_BV(TOIE1);
    TCCR1B=_BV(CS10);
    sei();
    Lpx4HybridCore decoder;
    uint8_t cursor=1;
    for(int8_t x=-32;x<32 && !math_error;++x){
        for(uint8_t gain=0;gain<=14 && !math_error;gain+=2){
            for(int8_t amp=-16;amp<=16 && !math_error;++amp){
                for(uint8_t kind=0;kind<4 && !math_error;++kind){
                    cursor+=23;
                    const uint8_t lag=cursor&1?145:18;
                    const uint8_t earlier=cursor-lag;
                    const uint8_t idx=kind&1;
                    const uint8_t gap=kind==0?0:kind==1?1:kind==2?79:0;
                    const uint8_t count=kind==3?idx:idx+1;
#if LPX4_AVR5_SAMPLE_LEAF
                    decoder.gain_=gain<<4;
#else
                    decoder.gain_=gain;
#endif
                    decoder.lag_=lag;
                    decoder.ringCursor_=cursor;
                    decoder.pulseIndex_=idx;
                    decoder.pulseCount_=count;
                    decoder.pulsePos_[idx]=gap;
                    decoder.pulseAmp_[idx]=amp;
                    decoder.ringQ_[earlier]=x;
                    decoder.ringQ_[cursor]=73;
                    const uint16_t step=(uint16_t)((gain*7999u)^(cursor*251u));
                    decoder.blockStep_=step;
#if LPX4_AVR5_SAMPLE_LEAF
                    const int32_t excitation=decoder.decodeCompactAvr5(
                        reinterpret_cast<uint8_t*>(&decoder.blockStep_));
#else
                    int8_t q=0;
                    if(!decoder.decodeCode(q))math_error=1;
                    const int32_t excitation=lpx4Mul8xU16(q,step);
#endif
                    const int8_t quantized=expected(x,gain,kind==0?amp:0);
                    uint8_t zero;
                    __asm__ volatile("mov %0,__zero_reg__" : "=r"(zero));
                    if(zero) math_zero_error=1;
                    const uint8_t resultingIndex=idx+(kind==0);
                    // The consumed gap slot is dead. The asm countdown leaves
                    // 255 there; the C decoder retains zero after consumption.
                    const uint8_t resultingGap=kind==0?(LPX4_AVR5_SAMPLE_LEAF?255:0):
                        kind==3?gap:(uint8_t)(gap-1);
                    if(excitation!=(int32_t)quantized*step ||
                       decoder.ringCursor_!=(uint8_t)(cursor+1) ||
                       decoder.ringQ_[cursor]!=quantized || decoder.ringQ_[earlier]!=x ||
                       decoder.pulseIndex_!=resultingIndex ||
                       decoder.pulsePos_[idx]!=resultingGap)
                        math_error=1;
                    ++math_cases;
                }
            }
        }
    }
    math_done=1;
    for(;;){}
}
