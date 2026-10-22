/* MicroMusic LPX3-AVR Fast2 / ATmega328P, 16 MHz
 * Real-time audio: Timer1 8000 Hz -> Timer2 PWM D3 (OC2B) 62500 Hz.
 * LPC synthesis in foreground, optimized to TWO LSF->LPC polynomial
 * conversions per 160 samples (one-time extra at startup).
 * 512-byte ring buffers ~64 ms. Warm-start prebuffer ~=48 ms.
 * Wave data must be in PROGMEM; 32 KB chip Flash limit applies.
 * Pin D3 -> RC low-pass / amplifier input. Never drive a loudspeaker directly.
 * This is a firmware prototype: no physical hardware benchmark is claimed.
 * Conflict: Servo / tone / analogWrite(3,11) / libraries using Timer1/2.
 */
#include <Arduino.h>
#include <avr/pgmspace.h>
#include <util/atomic.h>
#include <avr/interrupt.h>
#include "Lpx3AvrCore.h"
#include "voice_data.h"

static Lpx3AvrCore decoder;
static uint8_t ring[512];
static volatile uint16_t head = 0, tail = 0;
static volatile bool endOfStream=false, completed=false;
static volatile uint32_t underrunCount=0;

static uint8_t readProgmem(void* context,uint16_t offset){
   const uint8_t* p=(const uint8_t*)context;
   return pgm_read_byte_near(p+offset);
}
static uint16_t fillLevel(){
   uint16_t h,t;
   ATOMIC_BLOCK(ATOMIC_RESTORESTATE){h=head;t=tail;}
   return (h-t)&511;
}
static void fillAudio(uint16_t target){
   while(!endOfStream){
      uint16_t h,t;
      ATOMIC_BLOCK(ATOMIC_RESTORESTATE){h=head;t=tail;}
      if(((h-t)&511U)>=target)break;
      uint16_t next=(h+1)&511;
      if(next==t)break;
      uint8_t pcm;
      if(!decoder.next(pcm)){
         endOfStream=true;
         break;
      }
      ring[h]=pcm;
      // Only the 16-bit head store needs to be atomic w.r.t. the ISR.
      ATOMIC_BLOCK(ATOMIC_RESTORESTATE){head=next;}
   }
}
ISR(TIMER1_COMPA_vect){
   const uint16_t t=tail;
   if(t!=head){
       OCR2B=ring[t];
       tail=(t+1)&511;
   }else{
       OCR2B=128;
       if(endOfStream){TIMSK1&=(uint8_t)~_BV(OCIE1A);completed=true;}
       else ++underrunCount;
   }
}
static void startPWM(){
   // OC2B is PD3, Arduino pin 3. 8-bit Fast PWM, prescaler 1.
   pinMode(3,OUTPUT);
   OCR2B=128;
   TCCR2A=_BV(COM2B1)|_BV(WGM21)|_BV(WGM20);
   TCCR2B=_BV(CS20);
   // Timer1 sample interrupt 16MHz/(1999+1) = 8kHz.
   TCCR1A=0;TCCR1B=0;
   TCNT1=0;
   OCR1A=(F_CPU/8000UL)-1UL;
   TIFR1=_BV(OCF1A);
   TCCR1B=_BV(WGM12)|_BV(CS10);
   TIMSK1|=_BV(OCIE1A);
}
void setup(){
    Serial.begin(115200);
    if(F_CPU!=16000000UL){Serial.println(F("F_CPU must be 16 MHz"));return;}
    if(!decoder.begin(readProgmem,(void*)g_voice_l3av,sizeof(g_voice_l3av))){
        Serial.print(F("Invalid L3AV: "));Serial.println((int)decoder.error());return;
    }
    fillAudio(384); // 48ms prebuffer: Timer1 not enabled yet.
    noInterrupts();startPWM();interrupts();
    Serial.println(F("LPX3-AVR Fast2 playback started"));
}
void loop(){
    if(!completed){fillAudio(480);return;}
    static bool reported=false;
    if(!reported){
        reported=true;uint32_t n;
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE){n=underrunCount;}
        Serial.print(F("Done. Underruns: "));Serial.println(n);
        Serial.print(F("Decoder error: "));Serial.println((int)decoder.error());
    }
}
