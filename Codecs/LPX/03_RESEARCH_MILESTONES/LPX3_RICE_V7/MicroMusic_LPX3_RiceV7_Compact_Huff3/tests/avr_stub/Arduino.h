#pragma once
#include <stdint.h>
#define F_CPU 16000000UL
#define OUTPUT 1
#define _BV(bit) (1u<<(bit))
#define F(lit) lit
extern void pinMode(uint8_t,uint8_t);
extern void noInterrupts();
extern void interrupts();
struct MockSerial {void begin(unsigned long);void print(const char*);void print(uint32_t);void println(const char*);void println(uint32_t);};
extern MockSerial Serial;
extern volatile uint8_t TCCR1A,TCCR1B,TIMSK1,TCCR2A,TCCR2B,TCCR0A,TCCR0B,TIMSK0,TIFR0,TIFR1,TCNT0,OCR0A,OCR2B,PORTD,DDRD;
extern volatile uint16_t TCNT1;
enum {PD4=4, DDD4=4, CS10=0, CS11=1,CS20=0,CS01=1,TOV1=0, TOIE1=0, COM2B1=5,WGM21=1,WGM20=0,WGM01=1,OCF0A=1,OCIE0A=1};
