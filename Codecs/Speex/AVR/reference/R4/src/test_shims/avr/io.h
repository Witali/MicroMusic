#ifndef AVR_IO_H
#define AVR_IO_H
#include <stdint.h>
#define _BV(bit) (1U<<(bit))
#define DDB1 1
#define COM1A1 7
#define WGM10 0
#define WGM12 3
#define CS10 0
#define WGM21 1
#define CS21 2
#define OCIE2A 1
#define DDRB (*(volatile uint8_t*)0x24)
#define TCCR1A (*(volatile uint8_t*)0x80)
#define TCCR1B (*(volatile uint8_t*)0x81)
#define OCR1A (*(volatile uint8_t*)0x88)
#define TCCR2A (*(volatile uint8_t*)0xB0)
#define TCCR2B (*(volatile uint8_t*)0xB1)
#define OCR2A (*(volatile uint8_t*)0xB3)
#define TCNT2 (*(volatile uint8_t*)0xB2)
#define TIMSK2 (*(volatile uint8_t*)0x70)
#endif
