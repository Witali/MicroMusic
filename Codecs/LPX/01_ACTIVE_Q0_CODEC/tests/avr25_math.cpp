// Direct arithmetic/ABI probe. Inputs are supplied externally, never test tables
// in firmware. Timer1 overflow stays active during every arithmetic call.
#include <avr/io.h>
#include <avr/interrupt.h>
#include "Lpx4Math.h"
extern "C" {
volatile uint8_t math_ready,math_kind,math_t,math_bits;
volatile uint16_t math_irqs;
int16_t math_x,math_y,math_a[10],math_h[20];
int32_t math_exc;
volatile int32_t math_out;
__attribute__((noinline,used)) void math_case(){
    switch(math_kind){
    case 0:math_out=lpx4Mul16(math_x,math_y);break;
    case 1:math_out=lpx4Mul8x16((int8_t)math_x,math_y);break;
    case 2:math_out=lpx4Mul8xU16((int8_t)math_x,(uint16_t)math_y);break;
    case 3:math_out=lpx4PitchQ4((int8_t)math_x,(uint8_t)math_y);break;
    case 4:math_out=lpx4AttenuateQ14((uint16_t)math_y,math_x);break;
    case 5:
        if(math_bits==2)math_out=lpx4LpcInterpolate(math_x,math_y,math_t,2);
        else if(math_bits==3)math_out=lpx4LpcInterpolate(math_x,math_y,math_t,3);
        else math_out=lpx4LpcInterpolate(math_x,math_y,math_t,4);
        break;
    case 6:math_out=lpx4PwmQ14(math_x,(uint8_t)math_y);break;
    case 7:math_out=lpx4SynthesisQ12<true>(math_exc,math_a,math_h);break;
    case 8:math_out=lpx4Clip15From24(math_exc);break;
    case 9:math_out=lpx4AttenuateFixedQ14<13094>(math_x);break;
    case 10:math_out=lpx4AttenuateFixedQ14<64>(math_x);break;
    case 11:math_out=lpx4AttenuateFixedQ14<7800>(math_x);break;
    case 12:math_out=lpx4Shift12(math_exc);break;
    case 13:math_out=lpx4Shift14(math_exc);break;
    case 14:math_out=lpx4Mul32x16(math_exc,math_y);break;
    case 15:math_out=lpx4AddClip15(math_x,math_y);break;
    case 16:math_out=lpx4AttenuateFixedQ14<8192>(math_x);break;
    case 17:math_out=lpx4AttenuateFixedQ14<0>(math_x);break;
    case 18:math_out=lpx4AttenuateFixedQ14<16384>(math_x);break;
    case 19:math_out=lpx4AttenuateFixedQ14<13926>(math_x);break;
    case 20:math_out=lpx4AttenuateFixedQ14<11469>(math_x);break;
    case 21:math_out=lpx4AttenuateFixedQ14<1>(math_x);break;
    case 22:math_out=lpx4AttenuateFixedQ14<16383>(math_x);break;
    case 23:math_out=lpx4AttenuateFixedQ14<4096>(math_x);break;
    case 24:math_out=lpx4ClipQ14(math_x);break;
    case 25:math_out=lpx4SynthesisQ12<true,true>(math_exc,math_a,math_h);break;
    case 26:math_out=lpx4SynthesisQ12<false,true>(math_exc,math_a,math_h);break;
    case 27:math_out=lpx4SynthesisQ12<false>(math_exc,math_a,math_h);break;
    case 28:math_out=lpx4PitchQ4((int8_t)math_x,(uint8_t)math_y,true);break;
    }
}
}
ISR(TIMER1_OVF_vect){++math_irqs;}
int main(){
    TIMSK1=_BV(TOIE1);TCCR1A=_BV(WGM10);TCCR1B=_BV(WGM12)|_BV(CS10);
    sei();math_ready=1;for(;;){}
}
