/* Device access is deliberately separate from the portable musical engine. */
#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/wdt.h>
#include <stddef.h>
#include "engine.h"
#include "storage.h"
#include "clock.h"
#ifndef __AVR_ATtiny88__
#error "This hardware driver requires ATtiny88 (-mmcu=attiny88)"
#endif
#define VIRTUAL_NUMERATOR 19200000UL
_Static_assert(sizeof(UMVoice)==23,"UM88 AVR voice layout");
_Static_assert(offsetof(UMState,count)==216,"UM88 AVR count offset");
volatile uint8_t um_ring[192] __attribute__((aligned(64),section(".noinit")));
volatile uint8_t um_read,um_write,um_underruns;
volatile uint16_t um_samples;
#if !defined(UM_ENABLE_AVR_ASM) || !UM_ENABLE_AVR_ASM
ISR(TIMER1_OVF_vect) {
    uint8_t at=um_read;
    if(at!=um_write){OCR1AL=um_ring[at];OCR1BL=um_ring[at+1];um_read=at==190?0:at+2;}
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
int main(void) {
    cli();MCUSR=0;wdt_disable();CLKPR=_BV(CLKPCE);CLKPR=0;
    PRR=0;um_init();
    for(uint8_t i=0;i<192;i++)um_ring[i]=128;
    um_write=188;um_read=0;
    TCCR1A=0;TCCR1B=0;TCNT1=0;OCR1A=128;OCR1B=128;
    TCCR1A=_BV(COM1B1)|_BV(WGM10);
    if(UM_READ(UM_SONG_ADDRESS+5)==2){TCCR1A|=_BV(COM1A1);DDRB|=_BV(PB1);}
    DDRB|=_BV(PB2);TIFR1=_BV(TOV1);TIMSK1=_BV(TOIE1);TCCR1B=_BV(WGM12)|_BV(CS10);sei();
    uint32_t fraction=0,musicClock=0;
    uint8_t previousL=128,previousR=128;
    for(;;){
        /* Snapshot each shared cursor once: IRQ can wrap um_read between loads. */
        uint8_t consumer=um_read,producer=um_write;
        uint8_t queued=producer>=consumer?producer-consumer:producer-consumer+192;
        if(queued>182)continue;
        uint8_t advance=VIRTUAL_NUMERATOR/F_CPU;
        fraction+=VIRTUAL_NUMERATOR%F_CPU;
        if(fraction>=F_CPU){fraction-=F_CPU;advance++;}
        musicClock+=75000UL;
        if(musicClock>=F_CPU){musicClock-=F_CPU;um_tick();}
        uint32_t mixed=um_render();int8_t drum=percussion(advance);
        uint8_t targetL=um_output((int16_t)mixed+drum),targetR=um_output((int16_t)(mixed>>16)+drum),at=um_write;
        uint8_t midL=(previousL+targetL)>>1,midR=(previousR+targetR)>>1;
#define EMIT(l,r) do{um_ring[at]=(l);um_ring[at+1]=(r);at=at==190?0:at+2;}while(0)
        EMIT((previousL+midL)>>1,(previousR+midR)>>1);
        EMIT(midL,midR);
        EMIT((midL+targetL)>>1,(midR+targetR)>>1);
        EMIT(targetL,targetR);
#undef EMIT
        um_write=at;previousL=targetL;previousR=targetR;um_samples++;
    }
}
