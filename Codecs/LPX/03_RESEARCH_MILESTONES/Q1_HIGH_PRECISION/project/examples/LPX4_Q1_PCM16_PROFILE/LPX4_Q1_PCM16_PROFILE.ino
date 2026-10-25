/* LPX4 Q1 PCM16 profiler for ATmega328P 16 MHz. No PWM/audio ISR.
 * Output is decoded signed PCM16 only. Timer1 /1 measures elapsed CPU cycles;
 * occasional Timer1 overflow interrupt is INCLUDED in measured time.
 * Use this to characterize performance on hardware. It does not by itself
 * prove glitch-free 8kHz playback with a ring buffer.
 * Timer0 Arduino clock interrupt is disabled during the measurement.
 * Serial prints AFTER measurement. Stream data in voice_data.h PROGMEM.
 */
#include <Arduino.h>
#include <avr/pgmspace.h>
#include <avr/interrupt.h>
#include <util/atomic.h>
#include "Lpx4HybridCore.h"
#include "voice_data.h"
#if F_CPU!=16000000UL
#error "Run on a true 16 MHz ATmega328P board"
#endif
static_assert(sizeof(Lpx4HybridCore)<=650,"Decoder SRAM > 650 B");
static Lpx4HybridCore decoder;
static volatile uint16_t wrapHigh=0;
ISR(TIMER1_OVF_vect){++wrapHigh;}
uint32_t tick(){
  uint16_t hi,lo;uint8_t pending;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE){
    hi=wrapHigh;lo=TCNT1;pending=(uint8_t)(TIFR1&_BV(TOV1));
  }
  if(pending && lo<32768U)++hi;
  return ((uint32_t)hi<<16)|lo;
}
static bool finished=false;
void setup(){
  Serial.begin(115200);
  if(!decoder.begin(g_voice_l4hy,g_voice_l4hy_size)){
    Serial.print(F("LPX4 ERROR: "));Serial.println((int)decoder.error());
    finished=true;return;
  }
  TCCR1A=0;TCCR1B=0;TCNT1=0;wrapHigh=0;
  TIFR1=_BV(TOV1);TIMSK1=_BV(TOIE1);TCCR1B=_BV(CS10);
}
void loop(){
  if(finished)return;
  finished=true;
  const uint8_t oldTimsk0=TIMSK0;
  TIMSK0=0; // remove Arduino millis() ISR during profiling
  uint32_t sum=0,maxSample=0,sumWindow160=0,maxWindow160=0;
  uint32_t samples=0,over2000=0,over1600=0;
  uint16_t windowCount=0;
  uint16_t checksum=0;
  int16_t pcm=0;
  for(;;){
    const uint32_t a=tick();
    const bool ok=decoder.nextS16(pcm);
    const uint32_t b=tick();
    if(!ok)break;
    const uint32_t dt=b-a;sum+=dt;
    if(dt>maxSample)maxSample=dt;
    if(dt>2000)++over2000;
    if(dt>1600)++over1600;
    sumWindow160+=dt;
    if(++windowCount==160){
      if(sumWindow160>maxWindow160)maxWindow160=sumWindow160;
      sumWindow160=0;windowCount=0;
    }
    checksum=(uint16_t)(checksum^(uint16_t)pcm);
    ++samples;
  }
  if(windowCount&&sumWindow160>maxWindow160)maxWindow160=sumWindow160;
  TIMSK0=oldTimsk0;
  Serial.println(F("MicroMusic LPX4 fractional LPC Q1 / PCM16 diagnostic"));
  Serial.print(F("decoded samples: "));Serial.println(samples);
  Serial.print(F("decoder status: "));Serial.println((int)decoder.error());
  Serial.print(F("checksum: "));Serial.println(checksum,HEX);
  Serial.print(F("total CPU ticks: "));Serial.println(sum);
  Serial.print(F("average ticks/sample: "));Serial.println(samples?sum/samples:0);
  Serial.print(F("max nextS16() ticks: "));Serial.println(maxSample);
  Serial.print(F("max 160-sample window ticks: "));Serial.println(maxWindow160);
  Serial.print(F("samples over 1600 ticks: "));Serial.println(over1600);
  Serial.print(F("samples over 2000 ticks: "));Serial.println(over2000);
  Serial.print(F("mean decoder budget <=1600: "));
  Serial.println((samples>0 && sum/samples<=1600)?F("MEETS CPU MEAN TARGET"):F("OVER CPU MEAN TARGET"));
  Serial.println(F("NO CLAIM of real-time playback: ring/ISR not exercised."));
}
