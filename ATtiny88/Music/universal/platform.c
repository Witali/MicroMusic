/* Device access is deliberately separate from the portable musical engine. */
#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/wdt.h>
#include <stddef.h>
#include "engine.h"
#include "storage.h"
#include "clock.h"
#include "rational-clocks.h"
#include "audio-buffer.h"
#ifndef __AVR_ATtiny88__
#error "This hardware driver requires ATtiny88 (-mmcu=attiny88)"
#endif
#define VIRTUAL_NUMERATOR 19200000UL
_Static_assert(sizeof(UMVoice)==23,"UM88 AVR voice layout");
_Static_assert(offsetof(UMState,count)==216,"UM88 AVR count offset");
/* A page-local FIFO lets the optional ISR use its cursor as X low directly.
 * The builder still checks the resulting end address and stack reserve. */
volatile uint8_t um_ring[UM_PWM_BUFFER_FRAMES] __attribute__((aligned(256),section(".noinit")));
volatile uint8_t um_read,um_write,um_underruns;
volatile uint16_t um_samples;
#if defined(UM_BOARD_MH_ET_LIVE_16MHZ) && UM_BOARD_MH_ET_LIVE_16MHZ
/* Micronucleus enters the application through its reset vector, without a
 * peripheral reset. Follow avr-libc's documented .init3 watchdog pattern:
 * disable it before the CRT clears BSS, while r1 and SP are already valid.
 * Register names come from the retained Microchip DFP, never local addresses. */
void um_board_reset(void) __attribute__((naked,used,section(".init3")));
void um_board_reset(void) {
    cli();MCUSR=0;wdt_reset();wdt_disable();
    CLKPR=_BV(CLKPCE);CLKPR=0;PRR=0;
    EIMSK=0;PCICR=0;TIMSK0=0;TIMSK1=0;
    TCCR0A=0;TCCR1B=0;TCCR1A=0;GTCCR=0;
    ADCSRA=0;ACSR=0;SPCR=0;TWCR=0;EECR=0;SMCR=0;
    DDRB=0;PORTB=0;
}
#endif
#if !defined(UM_ENABLE_AVR_ASM) || !UM_ENABLE_AVR_ASM
ISR(TIMER1_OVF_vect) {
    uint8_t at=um_read;
    if(at!=um_write){
#if UM_OUTPUT_CHANNELS == 2
        OCR1AL=um_ring[at++];
#endif
        OCR1BL=um_ring[at++];
        um_read=at==UM_PWM_BUFFER_FRAMES?0:at;
    }
    else um_underruns++;
}
#endif
static int8_t percussion(uint8_t advance) {
    uint8_t mode=um.drumMode;
    if(!(mode&128))return 0;
    int8_t q;
    if((mode&3)==0){
        um.drumPhase+=advance;
        uint8_t phase=um.drumPhase;
        if(phase&128)phase=~phase;
        q=((int8_t)(phase-61))>>2;
    }else{
        uint16_t noise=um.drumPhase|((uint16_t)um.noiseHigh<<8);
        uint8_t carry=noise>>15;noise<<=1;if(carry)noise^=45;
        um.drumPhase=noise;um.noiseHigh=noise>>8;
        uint8_t low=noise;
        q=((mode&3)==1)?(int8_t)(((low>>1)&63)-(low&63)):(int8_t)(((low>>1)&63)-32);
        q>>=2;
    }
    q>>=(mode>>2)&3;
    if(mode&16)q=(q+4)>>3;
    return q;
}
#if UM_OUTPUT_CHANNELS == 2
/* Four exact quarter points, shared by the stereo channels. The accumulator stays
 * between 0 and 1020, including a decreasing ramp. These integer points equal
 * the original nested midpoint averages for every pair of 8-bit endpoints. */
static __attribute__((noinline)) uint8_t interpolate(uint8_t at,uint8_t stride,
                                                   uint8_t previous,uint8_t target) {
    uint16_t value=(uint16_t)previous*4;
    int16_t change=(int16_t)target-previous;
    for(uint8_t i=0;i<4;i++){
        value+=change;um_ring[at]=value>>2;
        at+=stride;if(at>=UM_PWM_BUFFER_FRAMES)at-=UM_PWM_BUFFER_FRAMES;
    }
    return at;
}
#endif
int main(void) {
#if !defined(UM_BOARD_MH_ET_LIVE_16MHZ) || !UM_BOARD_MH_ET_LIVE_16MHZ
    cli();MCUSR=0;wdt_disable();CLKPR=_BV(CLKPCE);CLKPR=0;
#endif
    PRR=0;um_init();
    const uint8_t reserve=4*UM_OUTPUT_CHANNELS;
    for(uint8_t i=0;i<UM_PWM_BUFFER_FRAMES;i++)um_ring[i]=128;
    um_write=UM_PWM_BUFFER_FRAMES-reserve;um_read=0;
    TCCR1A=0;TCCR1B=0;TCNT1=0;
#if UM_OUTPUT_CHANNELS == 2
    OCR1A=128;
#endif
    OCR1B=128;
    TCCR1A=_BV(COM1B1)|_BV(WGM10)
#if UM_OUTPUT_CHANNELS == 2
        |_BV(COM1A1)
#endif
        ;
    DDRB|=_BV(PB2)
#if UM_OUTPUT_CHANNELS == 2
        |_BV(PB1)
#endif
        ;
    TIFR1=_BV(TOV1);TIMSK1=_BV(TOIE1);TCCR1B=_BV(WGM12)|_BV(CS10);sei();
    UMFraction fraction=0;UMMusicClock musicClock=0;
    uint8_t previousL=128;
#if UM_OUTPUT_CHANNELS == 2
    uint8_t previousR=128;
#endif
    const uint8_t maximumQueued=UM_PWM_BUFFER_FRAMES-reserve-1;
    for(;;){
        /* Snapshot each shared cursor once: IRQ can wrap um_read between loads. */
        uint8_t consumer=um_read,producer=um_write;
        uint8_t queued=producer>=consumer?producer-consumer:producer-consumer+UM_PWM_BUFFER_FRAMES;
        if(queued>maximumQueued)continue;
        uint8_t advance=VIRTUAL_NUMERATOR/F_CPU;
        fraction+=UM_DRUM_FRACTION_INCREMENT;
        if(fraction>=UM_DRUM_FRACTION_PERIOD){fraction-=UM_DRUM_FRACTION_PERIOD;advance++;}
        musicClock+=UM_CONTROL_INCREMENT;
        if(musicClock>=UM_CONTROL_PERIOD){musicClock-=UM_CONTROL_PERIOD;um_tick();}
        UMSample mixed=um_render();int8_t drum=percussion(advance);
        uint8_t targetL=um_output((int16_t)mixed+drum),at=um_write;
#if UM_OUTPUT_CHANNELS == 1
            /* Producer is aligned to four bytes; capacity is divisible by four.
             * The complete mono batch is contiguous, including at wrap. */
            uint8_t mid=(previousL+targetL)>>1;
            volatile uint8_t *output=um_ring+at;
            output[0]=(previousL+mid)>>1;output[1]=mid;
            output[2]=(mid+targetL)>>1;output[3]=targetL;
            at+=4;if(at==UM_PWM_BUFFER_FRAMES)at=0;
#else
            uint8_t targetR=um_output((int16_t)(mixed>>16)+drum);
            uint8_t next=interpolate(at,2,previousL,targetL);
            interpolate(at+1,2,previousR,targetR);at=next;
            previousR=targetR;
#endif
        um_write=at;previousL=targetL;um_samples++;
    }
}
