/* HOST-ONLY stub for GCC syntax validation. Not for PIC build! */
#ifndef XC_H
#define XC_H
#include <stdint.h>
#define __interrupt()
static volatile uint8_t OSCCON,ANSELA,TRISA,PWM3CON,PR2,TMR2,PWM3DCH,PWM3DCL,T2CON;
static volatile struct {unsigned TMR2IF:1;} PIR1bits;
static volatile struct {unsigned TMR2IE:1;} PIE1bits;
static volatile struct {unsigned GIE:1,PEIE:1;} INTCONbits;
#endif
