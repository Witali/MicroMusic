/* MicroMusic LPX3 Rice V7 for ATmega328P @ 16 MHz.
 * Arduino Nano/Uno; Timer0 generates 8kHz ISR, Timer2 62.5kHz PWM (D3).
 * 512 B ring buffer, prefill 384 samples (48ms), foreground LPC decoding.
 * Real CPU timing / zero-underruns MUST be verified on target board.
 * This sketch uses Timer0; Arduino millis/micros/delay become unavailable.
 * Timer1 /8 counts CPU cycles (8-cycle resolution) in profiling mode.
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
static uint16_t counterWraps=0;
static uint16_t ambiguousLongOperations=0;
static volatile uint16_t minQueueDuringPlayback=512;
static uint32_t measuredSamples=0;
static uint8_t count20=0;
#endif
static void fillAudio(uint16_t goal){
   while(!streamEnded){
      uint16_t h,t;
      ATOMIC_BLOCK(ATOMIC_RESTORESTATE){h=head;t=tail;}
      if(((h-t)&511U)>=goal||((h+1)&511U)==t)break;
      uint8_t pcm=128;
#if LPX3_PROFILE
      // Timer1 /8 provides 8-cycle measurement granularity. D4 scope pulse.
      PORTD |= _BV(PD4);
      const uint16_t before=TCNT1;
      TIFR1=_BV(TOV1);
#endif
      const bool ok=decoder.next(pcm);
#if LPX3_PROFILE
      const uint16_t after=TCNT1;
      PORTD &= (uint8_t)~_BV(PD4);
      const uint32_t dt=(uint32_t)((uint16_t)(after-before))*8u;
      const bool overflow=(TIFR1&_BV(TOV1))!=0;
      if(overflow)++counterWraps;
      // Conservative long-operation alert if >one full Timer1 revolution.
      if(overflow && after>=before)++ambiguousLongOperations;
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
    // Timer1 /8: 0.5 us ticks, one overflow spans ~32.768 ms.
    // Avoids 16-bit wrap for any plausible LPC conversion peak.
    TCCR1A=0;TCCR1B=_BV(CS11);TCNT1=0;TIMSK1=0;
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
    TCCR1A=0;TCCR1B=_BV(CS11);TCNT1=0;
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
    Serial.print(F("Max next() cycles (~8-cycle precision): "));Serial.println(maxSampleCycles);
    Serial.print(F("Max 20-call sum cycles: "));Serial.println(max20Cycles);
    Serial.print(F("Total measured cycles: "));Serial.println(totalCycles);
    Serial.print(F("Samples measured: "));Serial.println(measuredSamples);
    Serial.print(F("Average next() cycles: "));
    Serial.println(measuredSamples ? totalCycles/measuredSamples : 0u);
    Serial.print(F("Min ring occupancy while active: "));Serial.println(minQueueDuringPlayback);
    Serial.print(F("Timer1 wraps seen: "));Serial.println(counterWraps);
    Serial.print(F("Ambiguous >=524288 cycle operations: "));Serial.println(ambiguousLongOperations);
    Serial.println(F("Timer1 resolution: 8 CPU cycles; values include preempting ISRs."));
    Serial.println(F("8000Hz = 2000 cycles/sample avg; 20-call budget = 40000 cycles"));
    Serial.println(F("Report acquired on BOARD only. Profile overhead is conservative."));
#endif
}
