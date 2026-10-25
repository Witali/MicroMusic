#pragma once
#include <stdint.h>
#define F_CPU 16000000UL
#define OUTPUT 1
#define F(x) x
#define UINT32_MAX 0xffffffffUL
#define _BV(b) (1U << (b))
#define PD4 4
#define DDD4 4
#define CS10 0
#define TOV1 0
#define TOIE1 0
#define COM2B1 5
#define WGM21 1
#define WGM20 0
#define CS20 0
#define WGM01 1
#define OCF0A 1
#define OCIE0A 1
#define CS01 1
class TinySerial {
 public:
  void begin(uint32_t);
  template<typename T> void print(T);
  template<typename T> void println(T);
};
extern TinySerial Serial;
void pinMode(uint8_t,uint8_t);
void noInterrupts();
void interrupts();
extern volatile uint8_t DDRD,PORTD,OCR2B,TCCR2A,TCCR2B,TCCR0A,TCCR0B,TCNT0,OCR0A,TIFR0,TIMSK0,TCCR1A,TCCR1B,TIMSK1,TIFR1;
extern volatile uint16_t TCNT1;
