/* MicroMusic / L3AV Fast2: measurement firmware for ATmega328P @ 16 MHz.
 * Timer2 8-bit Fast PWM on D3/OC2B, carrier 62500 Hz.
 * Timer0 CTC OCR0A=249 with /8 prescale -> exact 8000 sample ISR/s.
 * Timer1 is FREE RUNNING (no prescaler), measures decoder.next() CPU cycles.
 * D4/PD4 = logic-analyzer probe high WHILE decoder.next() executes.
 * NO DECODING OR SERIAL PRINTS INSIDE ANY TIMER ISR.
 * Arduino millis(), micros(), delay(), Servo/tone/analogWrite() timers clash.
 * This is a physical measurement harness, NOT evidence of measured board cycles.
 */
#include <Arduino.h>
#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/pgmspace.h>
#include <util/atomic.h>
#include "Lpx3AvrCore.h"
#include "voice_data.h"
#if F_CPU != 16000000UL
#error ATmega328P @ 16MHz is required for 8000Hz Timer0 configuration
#endif

static Lpx3AvrCore decoder;
static uint8_t ring[512];
static volatile uint16_t head=0,tail=0;
static volatile uint32_t underruns=0,played=0;
static volatile bool streamEnded=false,done=false;
static uint16_t lowestLevel=511;

// Category 0 = ordinary sample, 1 = 20-sample LPC interpolation,
// 2 = 80-sample excitation header, 3 = 160-sample LPC/frame update.
struct Timing {uint16_t maxCycles;uint32_t sumCycles;uint32_t n;};
static Timing timing[4];
static uint32_t peakSubframeCycles=0;
static uint32_t subframeSum=0;
static uint8_t subframeN=0;
static uint16_t suspiciousWraps=0;
static uint8_t count20=0,count80=0,count160=0;

static uint8_t flashByte(void* ctx,uint16_t off){
    return pgm_read_byte_near((const uint8_t*)ctx+off);
}
static uint16_t ringFill(){
    uint16_t h,t;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE){h=head;t=tail;}
    return (h-t)&511U;
}

ISR(TIMER0_COMPA_vect){
    uint16_t t=tail;
    if(t!=head){
        OCR2B=ring[t];
        tail=(t+1)&511U;
        ++played;
    }else{
        OCR2B=128;
        if(streamEnded){TIMSK0&=(uint8_t)~_BV(OCIE0A);done=true;}
        else ++underruns;
    }
}
static void startOutput(){
    pinMode(3,OUTPUT); // PD3 OC2B
    pinMode(4,OUTPUT); // PD4 diagnostic pulse
    PORTD&=(uint8_t)~_BV(PD4);
    OCR2B=128;
    TCCR2A=_BV(COM2B1)|_BV(WGM21)|_BV(WGM20);
    TCCR2B=_BV(CS20);
    // Timer1 continues free running; do NOT put Timer1 in CTC mode.
    TCCR0A=_BV(WGM01); // CTC
    TCCR0B=0;
    TCNT0=0;
    OCR0A=249;
    TIFR0=_BV(OCF0A);
    TIMSK0=_BV(OCIE0A); // disables Arduino millis() overflow IRQ
    TCCR0B=_BV(CS01); // prescaler /8
}

static void fillAudio(uint16_t target){
    while(!streamEnded){
        uint16_t level=ringFill();
        if(level<lowestLevel)lowestLevel=level;
        if(level>=target)break;
        uint16_t h,t;
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE){h=head;t=tail;}
        const uint16_t nh=(h+1)&511U;
        if(nh==t)break;
        // Three 8-bit counters avoid slow 32-bit modulo in the hot path.
        const uint8_t cat=(count160==0)?3:((count80==0)?2:((count20==0)?1:0));
        uint8_t pcm;
        // Timer1 /1: one hardware tick = exactly one CPU clock.
        const uint16_t start=TCNT1;
        PORTD|=_BV(PD4);
        const bool ok=decoder.next(pcm);
        PORTD&=(uint8_t)~_BV(PD4);
        const uint16_t cycles=(uint16_t)(TCNT1-start);
        if(!ok){streamEnded=true;break;}
        Timing& r=timing[cat];
        if(cycles>r.maxCycles)r.maxCycles=cycles;
        r.sumCycles+=cycles;
        ++r.n;
        if(++count20==20)count20=0;
        if(++count80==80)count80=0;
        if(++count160==160)count160=0;
        subframeSum+=cycles;
        ++subframeN;
        if(subframeN==20){
            if(subframeSum>peakSubframeCycles)peakSubframeCycles=subframeSum;
            subframeSum=0;
            subframeN=0;
        }
        ring[h]=pcm;
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE){head=nh;}
        // A 16-bit timer has 4.096ms wrapping period @ 16MHz. Every decode
        // call must be shorter; use oscilloscope D4 for overflow-independent
        // measurements if a worst case approaches this duration.
        if(cycles>60000U)++suspiciousWraps;
    }
}

void setup(){
    Serial.begin(115200);
    // Timer1 measurement independent of Timer0 playback timer.
    TCCR1A=0;TIMSK1=0;TCCR1B=_BV(CS10);TCNT1=0;
    if(!decoder.begin(flashByte,(void*)g_voice_l3av,sizeof(g_voice_l3av))){
        Serial.print(F("L3AV ERROR "));Serial.println((int)decoder.error());
        done=true;return;
    }
    fillAudio(384);
    noInterrupts();startOutput();interrupts();
}
void loop(){
    if(!done){fillAudio(480);return;}
    static bool once=false;if(once)return;once=true;
    Serial.println(F("L3AV FAST2 CPU PROFILE (measured with Timer1 /1)"));
    Serial.print(F("Audio samples played: "));Serial.println(played);
    Serial.print(F("Underruns: "));Serial.println(underruns);
    Serial.print(F("Decoder error: "));Serial.println((int)decoder.error());
    Serial.print(F("Buffer low water: "));Serial.println(lowestLevel);
    Serial.print(F("Suspiciously long calls: "));Serial.println(suspiciousWraps);
    Serial.print(F("Peak sum of 20 consecutive decode calls (cycles): "));Serial.println(peakSubframeCycles);
    Serial.println(F("Category: counts, max cycles, mean cycles (decode-only)"));
    for(uint8_t i=0;i<4;i++){
        Serial.print(i);Serial.print(F(": "));
        Serial.print(timing[i].n);Serial.print(F(" / "));
        Serial.print(timing[i].maxCycles);Serial.print(F(" / "));
        Serial.println(timing[i].n?timing[i].sumCycles/timing[i].n:0);
    }
    Serial.println(F("Per-sample budget at 8000Hz/16MHz: 2000 cycles."));
    Serial.println(F("Use D4 pulse + analyzer if wrap/underrun occurs."));
}
