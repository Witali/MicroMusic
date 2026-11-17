// Exercise signed17 anchor differences and every Q8 interpolation phase.
#include <avr/interrupt.h>
#include "Lpx4Math.h"

extern "C" {
volatile uint32_t math_cases, math_irqs;
volatile uint8_t math_done, math_error, math_zero_error, math_backend;
}
ISR(TIMER1_OVF_vect) { ++math_irqs; }

static uint16_t randomState=7;
static int16_t previous[10], current[10], output[10];

__attribute__((noinline)) static void render(uint8_t phase){
    lpx4LpcInterpolateVectorPrepared(output,previous,current,phase);
}

int main(){
    math_backend=LPX4_USE_AVR_ASM;
    TIMSK1=_BV(TOIE1);
    TCCR1B=_BV(CS10);
    sei();
    const int16_t extremes[]={-32768,-32767,-16384,-4096,-255,-1,0,1,255,4096,16384,32766,32767};
    const uint16_t scenarios=LPX4_USE_AVR_ASM?1024:512;
    for(uint16_t scenario=0;scenario<scenarios && !math_error;++scenario){
        for(uint8_t tap=0;tap<10;++tap){
            randomState=randomState*421+19;
            previous[tap]=(int16_t)randomState;
            randomState=randomState*421+19;
            current[tap]=(int16_t)randomState;
            if(scenario<sizeof(extremes)/sizeof(extremes[0])){
                previous[tap]=extremes[scenario];
                current[tap]=extremes[(scenario+tap)%13];
            }
        }
        for(uint16_t phase=0;phase<256 && !math_error;++phase){
            render((uint8_t)phase);
            uint8_t zero;
            __asm__ volatile("mov %0,__zero_reg__" : "=r"(zero));
            if(zero)math_zero_error=1;
            for(uint8_t tap=0;tap<10;++tap){
                const int16_t expected=previous[tap]+((int32_t(current[tap])-previous[tap])*phase)/256;
                if(output[tap]!=expected)math_error=1;
                ++math_cases;
            }
        }
    }
    math_done=1;
    for(;;){}
}
