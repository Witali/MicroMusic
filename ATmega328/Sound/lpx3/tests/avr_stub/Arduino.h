#pragma once
#include <stdint.h>
#define F_CPU 16000000UL
#define OUTPUT 1
#define _BV(n) (1U<<(n))
extern volatile uint8_t OCR2B,TCCR2A,TCCR2B,TCCR1A,TCCR1B,TIFR1,TIMSK1;
extern volatile uint16_t TCNT1,OCR1A;
enum {COM2B1=5,WGM21=1,WGM20=0,CS20=0,OCF1A=1,WGM12=3,CS10=0,OCIE1A=1};
void pinMode(uint8_t,uint8_t);void noInterrupts();void interrupts();
#define F(x) x
struct SerialClass {void begin(unsigned long);void print(const char*);void print(int);void println(const char*);void println(unsigned long);void println(int);void println(unsigned int);};
extern SerialClass Serial;
extern volatile uint8_t OCR0A,TCCR0A,TCCR0B,TCNT0,TIFR0,TIMSK0,PORTD;
enum {WGM01=1,CS01=1,OCF0A=1,OCIE0A=1,PD4=4};
