// Bare ATmega328P one-shot ROM player. No profiler counters or GPIO markers.
#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/atomic.h>
#include "player_config.h"
#include "Lpx4HybridCore.h"
#ifndef LPX_PLAYER_DATA_HEADER
#define LPX_PLAYER_DATA_HEADER "synthetic_voice.h"
#endif
#include LPX_PLAYER_DATA_HEADER
#ifndef LPX_PLAYER_SEGMENTS
#error voice_data.h must define LPX_PLAYER_SEGMENTS and lpx_voices/lpx_sizes
#endif
#if LPX_PLAYER_SEGMENTS<1 || LPX_PLAYER_SEGMENTS>255
#error Player supports 1..255 reset segments
#endif
static Lpx4HybridCore decoder;
static uint8_t segment;
// These are playback state, not instrumentation. The foreground owns head,
// eof/error; the ISR owns tail/stopped. State has C linkage for external tools.
extern "C" {
uint8_t lpx_player_queue[LPX_PLAYER_QUEUE];
volatile LpxPlayerIndex lpx_player_head,lpx_player_tail;
volatile uint8_t lpx_player_eof,lpx_player_error,lpx_player_stopped;
}
static inline void barrier(){__asm__ __volatile__("" ::: "memory");}
static inline LpxPlayerIndex advance(LpxPlayerIndex index){
#if LPX_PLAYER_QUEUE==256
    return (uint8_t)(index+1);
#else
    return (LpxPlayerIndex)((index+1)&(LPX_PLAYER_QUEUE-1));
#endif
}
static void stopTimer(){TCCR1B=0;TIMSK1=0;lpx_player_stopped=1;}
ISR(TIMER1_COMPA_vect){
    const LpxPlayerIndex head=lpx_player_head,tail=lpx_player_tail;
    uint8_t sample=128;
    if(head!=tail){
        barrier();sample=lpx_player_queue[tail];barrier();
        lpx_player_tail=advance(tail);
    }
    OCR2B=sample;
#if LPX_PLAYER_IRQ_LOAD
    __builtin_avr_delay_cycles(LPX_PLAYER_IRQ_LOAD);
#endif
    if(lpx_player_eof && lpx_player_head==lpx_player_tail)stopTimer();
}
static bool beginSegment(){
    return decoder.begin((const uint8_t*)pgm_read_ptr(&lpx_voices[segment]),
                         pgm_read_word(&lpx_sizes[segment]));
}
static void fail(){
    lpx_player_error=(uint8_t)decoder.error();
    if(!lpx_player_error)lpx_player_error=(uint8_t)Lpx4HybridCore::CORRUPT_STREAM;
    // Publish terminal failure before EOF; atomically handle the last queued
    // sample having already drained, so no extra empty timer tick is required.
    barrier();
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE){
        lpx_player_eof=1;
        if(lpx_player_head==lpx_player_tail)stopTimer();
    }
}
static bool produce(LpxPlayerIndex head,LpxPlayerIndex next){
    if(decoder.finished()){
        ++segment;
        if(!beginSegment()){fail();return false;}
    }
    uint8_t value;
    if(!decoder.next(value)){fail();return false;}
    const bool last=decoder.finished() && segment==LPX_PLAYER_SEGMENTS-1;
    lpx_player_queue[head]=value;barrier();
    // Atomic byte publication suffices normally. Final head+EOF are one
    // publication: otherwise an ISR could consume the last sample before EOF.
#if LPX_PLAYER_QUEUE<=256
    if(!last)lpx_player_head=next;
    else
#endif
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE){
        lpx_player_head=next;
        if(last)lpx_player_eof=1;
    }
    return true;
}
int main(){
    if(!beginSegment()){fail();lpx_player_stopped=1;for(;;){}}
    LpxPlayerIndex fill=0;
    while(fill<LPX_PLAYER_PREFILL && !lpx_player_eof){
        const LpxPlayerIndex head=lpx_player_head;
        if(!produce(head,advance(head)))break;
        ++fill;
    }
    if(lpx_player_error || !fill){lpx_player_stopped=1;for(;;){}}
    DDRD|=_BV(DDD3);
    TCCR2A=_BV(COM2B1)|_BV(WGM21)|_BV(WGM20);
    TCCR2B=_BV(CS20);OCR2B=128;
    TCCR1A=TCCR1B=0;TCNT1=0;OCR1A=1999;
    TIFR1=_BV(OCF1A);TIMSK1=_BV(OCIE1A);
    TCCR1B=_BV(WGM12)|_BV(CS10);sei();
    while(!lpx_player_eof){
        const LpxPlayerIndex head=lpx_player_head,next=advance(head);
        LpxPlayerIndex tail;
#if LPX_PLAYER_QUEUE<=256
        tail=lpx_player_tail;
#else
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE){tail=lpx_player_tail;}
#endif
        if(next!=tail)produce(head,next);
    }
    while(!lpx_player_stopped){}
    cli();for(;;){}
}
