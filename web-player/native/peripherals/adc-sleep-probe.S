/* Source-only sleep-entry ADC/ADIE acquisition; no silicon outcome assumed.
 * One SLEEP per reset. WDT interrupt independently ends the observation.
 * Build the four complete profiles in adc-sleep-probe.json; see its .md.
 */
#ifndef PROBE_PROFILE_ID
#error "Choose a complete profile from adc-sleep-probe.json"
#endif
#ifndef PROBE_SLEEP_MODE
#error "PROBE_SLEEP_MODE must select Idle 0 or ADC Noise Reduction 1"
#endif
#ifndef PROBE_ADIE
#error "PROBE_ADIE must be 0 or 1"
#endif
#if PROBE_PROFILE_ID < 1 || PROBE_PROFILE_ID > 255
#error "PROBE_PROFILE_ID must fit one nonzero byte"
#endif
#if PROBE_SLEEP_MODE < 0 || PROBE_SLEEP_MODE > 1 || PROBE_ADIE < 0 || PROBE_ADIE > 1
#error "Unsupported sleep/ADIE control"
#endif

#include "../attiny13a-registers.generated.inc"
.equ PROBE_WIRE_CLOCK_BIT,PORTB1
.equ PROBE_WIRE_DATA_BIT,PORTB4
.equ ADC_BASE,(1 << ADEN) | (1 << ADPS2) | (1 << ADPS1) | (PROBE_ADIE << ADIE)
.equ SLEEP_CONTROL,(1 << SE) | (PROBE_SLEEP_MODE << SM0)
.equ WATCHDOG_CONTROL,(1 << WDTIE)

.section .text
.global __vectors
__vectors:
 rjmp adc_sleep_reset
.rept WDT_vect_num - 1
 rjmp adc_sleep_unexpected_interrupt
.endr
 rjmp adc_sleep_watchdog_interrupt
 rjmp adc_sleep_adc_interrupt

adc_sleep_reset:
 cli
 ldi r16,RAMEND
 out SPL,r16
 clr r16
 out MCUSR,r16
 wdr
 ldi r16,(1 << WDCE) | (1 << WDE)
 out WDTCR,r16
 clr r16
 out WDTCR,r16
 out TIMSK0,r16
 out GIMSK,r16
 out MCUCR,r16
 out TCCR0B,r16
 out TCCR0A,r16
 out PRR,r16
 out ADCSRA,r16
 out ADCSRB,r16             /* ADATE=0; no auto-trigger source. */
 out PORTB,r16
 ldi r16,(1 << ACD)
 out ACSR,r16
 ldi r16,(1 << CLKPCE)
 out CLKPR,r16
 clr r16
 out CLKPR,r16              /* Continuous external 8 MHz, divider /1. */
 ldi r16,(1 << DDB0) | (1 << DDB1) | (1 << DDB4)
 out DDRB,r16
 ldi r16,(1 << ADC1D)
 out DIDR0,r16
 ldi r16,(1 << MUX0)
 out ADMUX,r16              /* ADC1/PB2, VCC reference, right adjusted. */
 ldi r16,ADC_BASE | (1 << ADIF)
 out ADCSRA,r16             /* ADEN=1, ADSC=0. No manual conversion anywhere. */

 clr r2
 clr r3
 ldi r16,5
 mov r4,r16                 /* Dedicated wire-v2 probe ID. */
 ldi r16,PROBE_PROFILE_ID
 mov r5,r16
 ldi r16,ADC_BASE
 mov r6,r16
 ldi r16,SLEEP_CONTROL
 mov r7,r16
 ldi r16,WATCHDOG_CONTROL
 mov r8,r16
 in r9,ADMUX
 in r10,DIDR0
 clr r11
 rcall probe_emit_frame     /* 0: planned controls; ADC already enabled. */

 inc r2
 in r6,ADCSRA
 in r7,ADCL
 in r8,ADCH
 in r9,SREG
 in r10,WDTCR
 ldi r16,1
 mov r11,r16
 rcall probe_emit_frame     /* 1: pre-sleep raw state, I=0, WDT still off. */

 clr r13                   /* Total ISR count; r14/r15 record first order. */
 clr r14
 clr r15
 clr r20                   /* ADC count/status/lo/hi/entry-SREG: r20..r24. */
 clr r21
 clr r22
 clr r23
 clr r24
 clr r25                   /* WDT count/status/lo/hi/entry-SREG: r25..r29. */
 clr r26
 clr r27
 clr r28
 clr r29
 wdr
 ldi r16,(1 << WDCE) | (1 << WDE)
 out WDTCR,r16
 ldi r16,WATCHDOG_CONTROL
 out WDTCR,r16             /* Interrupt only, /2K: nominal 16 ms, not calibrated. */
 ldi r16,SLEEP_CONTROL
 out MCUCR,r16
 sbi PORTB,PORTB0           /* Bracket the single sleep, transport remains idle. */
 sei
 sleep                     /* SEI's following instruction executes before IRQ. */
 cbi PORTB,PORTB0           /* First wake witness, not an exact ADC event time. */
 clr r16
 out MCUCR,r16             /* Never re-enter sleep after an early ADC wake. */
adc_sleep_wait_watchdog:
 tst r25
 breq adc_sleep_wait_watchdog
 cli                       /* Freeze all evidence before serialization. */
 in r1,ADCSRA
 in r19,ADCL
 in r30,ADCH
 in r31,SREG

 inc r2
 mov r6,r21
 mov r7,r22
 mov r8,r23
 mov r9,r24
 mov r10,r20
 ldi r16,2
 mov r11,r16
 rcall probe_emit_frame     /* 2: ADC ISR evidence; all zero if never entered. */
 inc r2
 mov r6,r26
 mov r7,r27
 mov r8,r28
 mov r9,r29
 mov r10,r25
 ldi r16,3
 mov r11,r16
 rcall probe_emit_frame     /* 3: independent watchdog ISR evidence. */
 inc r2
 mov r6,r14
 mov r7,r15
 mov r8,r13
 in r9,WDTCR
 in r10,MCUCR
 ldi r16,4
 mov r11,r16
 rcall probe_emit_frame     /* 4: ISR ordering, watchdog disabled, SE cleared. */
 inc r2
 mov r6,r1
 mov r7,r19
 mov r8,r30
 mov r9,r31
 mov r10,r13
 ldi r16,5
 mov r11,r16
 rcall probe_emit_frame     /* 5: final raw ADC state, saved before transport. */
adc_sleep_halt:
 rjmp adc_sleep_halt

adc_sleep_adc_interrupt:
 in r0,SREG                /* ADC vector acknowledgement already cleared ADIF. */
 push r0
 mov r24,r0
 in r21,ADCSRA
 in r22,ADCL                /* Raw low then high, no conversion fabricated. */
 in r23,ADCH
 inc r20
 inc r13
 mov r14,r13
 pop r0
 out SREG,r0
 reti

adc_sleep_watchdog_interrupt:
 in r0,SREG
 push r0
 push r16
 mov r29,r0
 in r26,ADCSRA
 in r27,ADCL
 in r28,ADCH
 inc r25
 inc r13
 mov r15,r13
 clr r16
 out WDTCR,r16             /* One independent interrupt; never a reset. */
 pop r16
 pop r0
 out SREG,r0
 reti

adc_sleep_unexpected_interrupt:
 cli
 rjmp adc_sleep_unexpected_interrupt

#include "probe-wire.inc"
