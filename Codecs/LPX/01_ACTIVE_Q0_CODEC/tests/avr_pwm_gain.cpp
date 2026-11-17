#include <avr/interrupt.h>
#include <stdint.h>
#include "gain.h"

extern "C" {
volatile uint32_t math_cases,math_irqs;
volatile uint8_t math_done,math_error,math_zero_error,math_backend;
volatile uint8_t requestedSample,requestedGain;
}
ISR(TIMER1_OVF_vect){++math_irqs;}

static __attribute__((noinline,noclone)) uint8_t render(uint8_t sample,uint8_t gain){return playbackGain(sample,gain);}

// Save the C caller's callee-saved registers, then verify the render function
// preserves every GNU AVR ABI register, including Y, with IRQs enabled.
static __attribute__((naked,noinline,noclone)) uint8_t abi(uint8_t,uint8_t){
    __asm__ volatile(
        ".irp n,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29\n\tpush r\\n\n\t.endr\n\t"
        ".irp n,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29\n\tldi r18,1+7*\\n\n\tmov r\\n,r18\n\t.endr\n\t"
        "rcall %x0\n\t"
        ".irp n,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,28,29\n\tldi r18,1+7*\\n\n\tcp r\\n,r18\n\tbrne 1f\n\t.endr\n\t"
        "rjmp 2f\n\t1: ldi r18,1\n\tsts math_error,r18\n\t2:\n\t"
        ".irp n,29,28,17,16,15,14,13,12,11,10,9,8,7,6,5,4,3,2\n\tpop r\\n\n\t.endr\n\tret"
        : : "i"(render));
}
int main(){
    math_backend=LPX4_USE_AVR_ASM||LPX4_USE_AVR_NOMUL_ASM;
    TIMSK1=_BV(TOIE1);TCCR1B=_BV(CS10);sei();
    for(uint16_t gain=128;gain<256 && !math_error;++gain)
        for(uint16_t sample=0;sample<256 && !math_error;++sample){
            requestedSample=sample;requestedGain=gain;
            const uint8_t actual=abi(requestedSample,requestedGain);
            uint8_t zero;__asm__ volatile("mov %0,__zero_reg__":"=r"(zero));
            if(zero)math_zero_error=1;
            const int32_t biased=((int32_t)sample*gain+64)/128+128-gain;
            const uint8_t expected=biased<0?0:biased>255?255:(uint8_t)biased;
            if(actual!=expected)math_error=1;
            ++math_cases;
        }
    math_done=1;for(;;){}
}
