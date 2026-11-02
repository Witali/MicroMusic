// One-shot ATtiny88 player. Device registers come from the pinned vendor DFP.
#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/pgmspace.h>
#include <util/atomic.h>
#include "Lpx4HybridCore.h"
#include "../../../../common/pwm_gain.h"
#ifndef __AVR_ATtiny88__
#error This hardware driver requires the real ATtiny88 target
#endif
#if F_CPU != 16000000UL
#error This playback clock requires 16 MHz
#endif
#ifndef LPX25_QUEUE
#define LPX25_QUEUE 32
#endif
#ifndef LPX25_REPEAT
#define LPX25_REPEAT 1
#endif
#if LPX25_QUEUE != 16 && LPX25_QUEUE != 24 && LPX25_QUEUE != 32
#error Select a 16, 24 or 32 byte queue
#endif
#if LPX25_REPEAT < 1 || LPX25_REPEAT > 255
#error Repeat count must be 1..255
#endif
static const uint8_t voice[] PROGMEM={
#include "audio.inc"
};
static Lpx4HybridCore decoder;
extern "C" {
// Retain OR addressing for power-of-two rings. A 24-byte array needs only
// byte alignment: 32-byte alignment would pad its ELF section back to 32.
uint8_t lpx25_queue[LPX25_QUEUE] __attribute__((used,externally_visible,aligned(LPX25_QUEUE==24?1:LPX25_QUEUE)));
volatile uint8_t lpx25_head,lpx25_tail,lpx25_eof,lpx25_stopped,lpx25_error;
}
static inline void barrier(){__asm__ __volatile__("" ::: "memory");}
static inline uint8_t advance(uint8_t at){
#if LPX25_QUEUE == 24
    return ++at==LPX25_QUEUE?0:at;
#else
    return (at+1)&(LPX25_QUEUE-1);
#endif
}
static void stop(){TCCR0A=0;TIMSK0=0;lpx25_stopped=1;}
#ifndef LPX25_ENABLE_ASM_ISR
#define LPX25_ENABLE_ASM_ISR 0
#endif
#if LPX25_ENABLE_ASM_ISR && defined(__AVR_ARCH__) && __AVR_ARCH__==25
#ifndef LPX25_ISR_FIXED_REGS
#error The reserved-register ISR requires whole-program -ffixed-r2 -ffixed-r3
#endif
ISR(TIMER0_COMPA_vect,ISR_NAKED){
    // r2/r3 are excluded from every foreground compilation. Z remains a
    // normal foreground pointer and is preserved. r1 is untouched throughout.
    __asm__ __volatile__(
        "in r3,%0\n\tpush r30\n\tpush r31\n\t"
        "lds r2,lpx25_head\n\tlds r30,lpx25_tail\n\tcp r2,r30\n\tbreq 2f\n\t"
#if LPX25_QUEUE == 24
        "ldi r31,0\n\tsubi r30,lo8(-(lpx25_queue))\n\tsbci r31,hi8(-(lpx25_queue))\n\t"
        "ld r2,Z\n\tsubi r30,lo8(lpx25_queue)\n\tinc r30\n\t"
        "cpi r30,24\n\tbrlo 4f\n\tclr r30\n\t4:\n\t"
#else
        "ldi r31,hi8(lpx25_queue)\n\tori r30,lo8(lpx25_queue)\n\t"
        "ld r2,Z\n\tinc r30\n\tandi r30,%3\n\t"
#endif
        "sts lpx25_tail,r30\n\trjmp 3f\n\t"
        "2: ldi r30,128\n\tmov r2,r30\n\t"
        "3: sts %1,__zero_reg__\n\tsts %2,r2\n\t"
        "pop r31\n\tpop r30\n\tout %0,r3\n\treti\n\t"
        : : "I"(_SFR_IO_ADDR(SREG)),"n"(_SFR_MEM_ADDR(OCR1AH)),"n"(_SFR_MEM_ADDR(OCR1AL)),
            "M"(LPX25_QUEUE==24?31:LPX25_QUEUE-1));
}
#else
ISR(TIMER0_COMPA_vect){
    uint8_t sample=128;
    const uint8_t tail=lpx25_tail;
    if(tail!=lpx25_head){
        barrier();sample=lpx25_queue[tail];barrier();
        lpx25_tail=advance(tail);
    }
    OCR1A=sample;
}
#endif
static bool begin(){return decoder.begin(voice,sizeof(voice));}
int main(){
    // Reset starts with interrupts masked. Keep the actual compiler CPU macros.
    CLKPR=_BV(CLKPCE);CLKPR=0;
    if(!begin()){lpx25_error=decoder.error();lpx25_stopped=1;for(;;){}}
    uint8_t repeats=LPX25_REPEAT;
    bool started=false;
    for(;;){
        if(lpx25_eof){
            // The foreground has no decoding left. Drain, then stop within a
            // few cycles of the final ISR return, before the next 2000-cycle
            // deadline. This keeps terminal bookkeeping out of every ISR.
            while(lpx25_head!=lpx25_tail){}
            ATOMIC_BLOCK(ATOMIC_RESTORESTATE){stop();}
            for(;;){}
        }
        const uint8_t head=lpx25_head,next=advance(head);
        if(next==lpx25_tail)continue;
        if(decoder.finished()){
            --repeats;
            if(!begin()){lpx25_error=decoder.error();break;}
        }
        uint8_t sample;
        // Zero-byte symbols delimit the actual production decode region for
        // an external observer. They add no firmware counters or instructions.
        __asm__ __volatile__(".global lpx25_decode_begin\nlpx25_decode_begin:" ::: "memory");
        const bool decoded=decoder.next(sample);
        __asm__ __volatile__(".global lpx25_decode_end\nlpx25_decode_end:" ::: "memory");
        if(!decoded){lpx25_error=decoder.error();break;}
        const bool last=decoder.finished() && repeats==1;
        lpx25_queue[head]=micromusic_pwm_gain(sample);barrier();
        // Final head and EOF are one publication, even with byte indices.
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE){lpx25_head=next;if(last)lpx25_eof=1;}
        if(!started && (next==LPX25_QUEUE*3/4 || last)){
            // OC1A/PB1, fast 8-bit PWM at 62.5 kHz. Timer0 CTC /8 gives 8 kHz.
            DDRB|=_BV(PB1);OCR1A=128;
            TCCR1A=_BV(COM1A1)|_BV(WGM10);TCCR1B=_BV(WGM12)|_BV(CS10);
            OCR0A=249;TCNT0=0;TIFR0=_BV(OCF0A);TIMSK0=_BV(OCIE0A);
            TCCR0A=_BV(CTC0)|_BV(CS01);started=true;sei();
        }
    }
    // Reject a prefill error; drain an already running valid prefix.
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE){
        lpx25_eof=1;
        if(!started || lpx25_head==lpx25_tail)stop();
    }
    if(started){while(lpx25_head!=lpx25_tail){};ATOMIC_BLOCK(ATOMIC_RESTORESTATE){stop();}}
    for(;;){}
}
