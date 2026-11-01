/* Source-only instruction-boundary control fixture. No programmer interface. */
#include "../../attiny13a-registers.generated.inc"
#define _AVR_IO_H_ 1
#define _SFR_IO8(address) (address)
#define _SFR_IO16(address) (address)
#include "../../../vendor/microchip/ATtiny_DFP/3.4.278/include/avr/iotn13a.h"
.section .text
.global __vectors, oracle_start, oracle_complete, oracle_unexpected, probe_callee
__vectors:
 rjmp oracle_start
 .rept 9
 rjmp oracle_unexpected
 .endr
oracle_start:
 cli
 clr r1
 ldi r16,RAMEND
 out SPL,r16
 out MCUSR,r1
 wdr
 ldi r16,(1<<WDCE)|(1<<WDE)
 out WDTCR,r16
 out WDTCR,r1
 out GIMSK,r1
 out TIMSK0,r1
 out ADCSRA,r1
 out PRR,r1
 out TCCR0A,r1
 out TCCR0B,r1
 out GTCCR,r1
 ldi r16,1<<ACD
 out ACSR,r16
 ldi r30,lo8(oracle_record)
 ldi r31,hi8(oracle_record)
 ldi r18,12+4*ORACLE_CASE_COUNT
1:
 st Z+,r1
 dec r18
 brne 1b
 out TCNT0,r1
 ldi r16,1<<CS00
 out TCCR0B,r16
#include "oracle-cases.generated.inc"
 ldi r16,0
 out TCCR0B,r16
oracle_complete:
 nop
 rjmp oracle_complete
probe_callee:
 inc r16
 ret
oracle_unexpected:
 ldi r16,0xee
 sts oracle_record,r16
 rjmp oracle_unexpected
