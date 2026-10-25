#define LPX3_PROFILE 1
#define LPX3_REPEAT_COUNT 20
/* MicroMusic LPX3 Rice V7 for ATmega328P @ 16 MHz.
 * Arduino Nano/Uno; Timer0 generates 8kHz ISR, Timer2 62.5kHz PWM (D3).
 * 512 B ring buffer, prefill 384 samples (48ms), foreground LPC decoding.
 * Real CPU timing / zero-underruns MUST be verified on target board.
 * This sketch uses Timer0; Arduino millis/micros/delay become unavailable.
 * Timer1 /1 counts CPU cycles (1-cycle resolution), extended via overflow ISR.
 * Measured durations INCLUDE profiler read overhead and preempting ISR cycles.
 * Do not connect a speaker directly to D3: RC LPF and amplifier needed.
 * Avoid Servo/tone/analogWrite 3 and 11 while this sketch runs.
 */
#include <Arduino.h>
#include <avr/pgmspace.h>
#include <util/atomic.h>
#include <avr/interrupt.h>
#include "Lpx3AvrCore.h"
#include "voice_data.h"
#ifndef LPX3_PROFILE
#define LPX3_PROFILE 0
#endif
#ifndef LPX3_REPEAT_COUNT
#define LPX3_REPEAT_COUNT 1
#endif
#if F_CPU != 16000000UL
#error MicroMusic LPX3 requires F_CPU=16000000UL
#endif
static Lpx3AvrCore decoder;
static uint8_t pcmRing[512];
static volatile uint16_t head=0,tail=0;
static volatile bool streamEnded=false,finished=false;
static uint16_t completedRuns=0;
static volatile uint32_t underruns=0;
#if LPX3_PROFILE
static uint32_t maxSampleCycles=0;
static uint32_t max20Cycles=0, totalCycles=0, last20Cycles=0;
static volatile uint16_t timer1High=0;
static uint32_t maxTimer1Overflows=0;
static volatile uint16_t minQueueDuringPlayback=512;
static uint32_t measuredSamples=0;
static uint8_t count20=0;
// Timer1 increments at 16MHz with no prescaler. Each overflow = 65536 cycles.
// Read low word and pending TOV1 atomically, compensating for an overflow
// that has occurred but whose interrupt has not yet been serviced.
ISR(TIMER1_OVF_vect) { ++timer1High; }
static uint32_t readTimer1Cycles(){
    uint16_t hi, lo;
    uint8_t pending;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE){
        hi=timer1High;
        lo=TCNT1;
        pending=(uint8_t)(TIFR1&_BV(TOV1));
    }
    if(pending && lo<0x8000U) ++hi;
    return ((uint32_t)hi << 16) | lo;
}
#endif
static void fillAudio(uint16_t goal){
   while(!streamEnded){
      uint16_t h,t;
      ATOMIC_BLOCK(ATOMIC_RESTORESTATE){h=head;t=tail;}
      if(((h-t)&511U)>=goal||((h+1)&511U)==t)break;
      uint8_t pcm=128;
#if LPX3_PROFILE
      // D4 pulse is visible on a scope; timer reads add small overhead.
      PORTD |= _BV(PD4);
      const uint32_t before=readTimer1Cycles();
#endif
      const bool ok=decoder.next(pcm);
#if LPX3_PROFILE
      const uint32_t after=readTimer1Cycles();
      PORTD &= (uint8_t)~_BV(PD4);
      const uint32_t dt=after-before;
      if(ok){
         if(dt>maxSampleCycles)maxSampleCycles=dt;
         last20Cycles+=dt;
         totalCycles+=dt;
         ++measuredSamples;
         if(++count20==20){
            if(last20Cycles>max20Cycles)max20Cycles=last20Cycles;
            last20Cycles=0;count20=0;
         }
      }
#endif
      if(!ok){
         if(decoder.error()||!decoder.finished()||(++completedRuns)>=LPX3_REPEAT_COUNT){
            streamEnded=true;break;
         }
         if(!decoder.begin(g_voice_l3av,g_voice_l3av_size)){
            streamEnded=true;break;
         }
         continue;
      }
      pcmRing[h]=pcm;
      // 16-bit head must be atomically published, after sample write.
      ATOMIC_BLOCK(ATOMIC_RESTORESTATE){head=(h+1)&511U;}
   }
}
ISR(TIMER0_COMPA_vect){
   const uint16_t t=tail;
#if LPX3_PROFILE
   if(!streamEnded){
      const uint16_t occupancy=(head-t)&511U;
      if(occupancy<minQueueDuringPlayback)minQueueDuringPlayback=occupancy;
   }
#endif
   if(t!=head){
      OCR2B=pcmRing[t];tail=(t+1)&511U;
   }else{
      OCR2B=128;
      if(streamEnded){TIMSK0&=(uint8_t)~_BV(OCIE0A);finished=true;}
      else ++underruns;
   }
}
static void setupTimers(){
    pinMode(3,OUTPUT); // OC2B = PD3 / D3
#if LPX3_PROFILE
    pinMode(4,OUTPUT); // diagnostic pulse from D4
    // Timer1 /1: 1 CPU cycle/tick; 65536-cycle overflow tracked by ISR.
    TCCR1A=0;TCCR1B=0;TCNT1=0;timer1High=0;
    TIFR1=_BV(TOV1);TIMSK1=_BV(TOIE1);TCCR1B=_BV(CS10);
#endif
    // Timer2 8bit Fast PWM on D3 = 16MHz/256 = 62.5kHz.
    OCR2B=128;
    TCCR2A=_BV(COM2B1)|_BV(WGM21)|_BV(WGM20);
    TCCR2B=_BV(CS20);
    // Timer0 CTC, 16MHz/(8*(249+1)) = 8kHz.
    TCCR0A=_BV(WGM01);TCCR0B=0;TCNT0=0;OCR0A=249;
    TIFR0=_BV(OCF0A);
    TIMSK0=_BV(OCIE0A);TCCR0B=_BV(CS01);
}
void setup(){
    Serial.begin(115200);
    if(!decoder.begin(g_voice_l3av,g_voice_l3av_size)){
      Serial.print(F("ERROR stream: "));Serial.println((int)decoder.error());return;
    }
#if LPX3_PROFILE
    TCCR1A=0;TCCR1B=0;TCNT1=0;timer1High=0;
    TIFR1=_BV(TOV1);TIMSK1=_BV(TOIE1);TCCR1B=_BV(CS10);
    DDRD|=_BV(DDD4);
#endif
    fillAudio(384);
    noInterrupts();setupTimers();interrupts();
    Serial.println(F("LPX3 Rice V7 playback started"));
}
void loop(){
    if(!finished){fillAudio(480);return;}
    static bool reported=false;
    if(reported)return;
    reported=true;
    uint32_t u;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE){u=underruns;}
    Serial.print(F("Underruns: "));Serial.println(u);
    Serial.print(F("Completed repeats: "));Serial.println(completedRuns);
    Serial.print(F("Decoder error: "));Serial.println((int)decoder.error());
#if LPX3_PROFILE
    Serial.print(F("Max next() cycles (1-cycle timer ticks): "));Serial.println(maxSampleCycles);
    Serial.print(F("Max 20-call sum cycles: "));Serial.println(max20Cycles);
    Serial.print(F("Total measured cycles: "));Serial.println(totalCycles);
    Serial.print(F("Samples measured: "));Serial.println(measuredSamples);
    Serial.print(F("Average next() cycles: "));
    Serial.println(measuredSamples ? totalCycles/measuredSamples : 0u);
    Serial.print(F("Min ring occupancy while active: "));Serial.println(minQueueDuringPlayback);
    Serial.println(F("Timer1: prescaler 1, 1 CPU cycle/tick; 16-bit overflows extended by ISR."));
    Serial.println(F("Measurement includes read overhead and preempting ISRs; use D4 to cross-check."));
    Serial.println(F("8000Hz = 2000 cycles/sample avg; 20-call budget = 40000 cycles"));
    Serial.println(F("Report acquired on BOARD only. Profile overhead is conservative."));
#endif
}
