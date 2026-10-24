/* Source-only ATtiny13A ADC ambiguity probe; no silicon outcome is assumed.
 * See adc-probe.json/md. Build as preprocessed AVR assembly, not host C.
 */
#ifndef PROBE_PROFILE_ID
#error "Choose PROBE_PROFILE_ID and its defines from adc-probe.json"
#endif
#ifndef PROBE_MODE
#define PROBE_MODE 0
#endif
#ifndef PROBE_ADIF_OPERATION
#define PROBE_ADIF_OPERATION 0
#endif
#ifndef PROBE_TRIALS
#define PROBE_TRIALS 2
#endif
#if PROBE_PROFILE_ID < 1 || PROBE_PROFILE_ID > 255
#error "PROBE_PROFILE_ID must fit one nonzero byte"
#endif
#if PROBE_MODE < 0 || PROBE_MODE > 2
#error "PROBE_MODE must be 0 first, 1 warmed normal, or 2 ADIF"
#endif
#if PROBE_ADIF_OPERATION < 0 || PROBE_ADIF_OPERATION > 6
#error "PROBE_ADIF_OPERATION must be 0 through 6"
#endif
#if PROBE_TRIALS < 1 || PROBE_TRIALS > 255
#error "PROBE_TRIALS must be 1 through 255"
#endif

#include "../attiny13a-registers.generated.inc"

.equ PROBE_WIRE_CLOCK_BIT,PORTB1
.equ PROBE_WIRE_DATA_BIT,PORTB4
.equ ADC_DIV64,(1 << ADPS2) | (1 << ADPS1)
.equ ADC_BASE,(1 << ADEN) | ADC_DIV64
#if PROBE_MODE == 2 && PROBE_ADIF_OPERATION == 2
/* Prepare ADIE with a whole byte BEFORE the conversion, never with SBI. */
.equ ADC_TRIAL_BASE,ADC_BASE | (1 << ADIE)
#else
.equ ADC_TRIAL_BASE,ADC_BASE
#endif
.equ ADC_START,ADC_TRIAL_BASE | (1 << ADSC) | (1 << ADIF)
.equ RECORD_BOOT,0
.equ RECORD_CONVERSION,1
.equ RECORD_ADIF_TEST,2
.equ RECORD_ADIF_CONTROL,3

.section .text
.global __vectors
__vectors:
 rjmp adc_probe_reset
.rept 9
 rjmp adc_probe_unexpected_interrupt
.endr

adc_probe_reset:
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
 out ADCSRB,r16             /* ADATE stays zero; no external trigger. */
 out PORTB,r16
 ldi r16,(1 << ACD)
 out ACSR,r16
 ldi r16,(1 << CLKPCE)
 out CLKPR,r16
 clr r16
 out CLKPR,r16              /* External 8 MHz CLKI, CPU divider /1. */
 ldi r16,(1 << DDB0) | (1 << DDB1) | (1 << DDB4)
 out DDRB,r16               /* Marker, trace clock/data; PB2/PB3 inputs. */
 ldi r16,(1 << ADC1D)
 out DIDR0,r16
 ldi r16,(1 << MUX0)
 out ADMUX,r16              /* ADC1/PB2, VCC reference, right adjusted. */
 clr r2
 clr r3
 ldi r16,3
 mov r4,r16
 ldi r16,PROBE_PROFILE_ID
 mov r5,r16
 ldi r16,ADC_START
 mov r6,r16
 in r7,ADMUX
 in r8,ADCSRB
 in r9,DIDR0
 in r10,SREG
 clr r11                   /* BOOT uses the documented config field map. */
 rcall probe_emit_frame

adc_probe_trial:
 inc r2
 brne adc_probe_sequence_ready
 inc r3
adc_probe_sequence_ready:
 ldi r16,(1 << ADIF)
 out ADCSRA,r16             /* ADC off, flag clear, prescaler held reset. */
 rcall adc_probe_recovery   /* Baseline may settle before the next trigger. */
#if PROBE_MODE == 1
 ldi r16,ADC_START
 out ADCSRA,r16             /* Unmeasured initialization conversion. */
 rcall adc_probe_wait_done
 /* Keep ADEN set. The measured conversion is now a normal conversion. */
#endif
 ldi r19,(1 << PORTB0)
 clr r20
 ldi r16,ADC_START
 in r8,ADCSRA               /* Before the measured ADSC OUT. */
 out PORTB,r19              /* Rising marker, one OUT before ADSC write. */
 out ADCSRA,r16             /* Full byte: ADEN+ADSC, old ADIF W1C. */
adc_probe_measured_wait:
 in r18,ADCSRA
 sbrc r18,ADSC
 rjmp adc_probe_measured_wait
 out PORTB,r20              /* Poll completion marker, NOT sample time. */

#if PROBE_MODE == 2
 in r8,ADCSRA               /* ADIF=1, ADSC=0; no following conversion. */
#if PROBE_ADIF_OPERATION == 0
 nop
 nop                       /* Two-cycle no-write control. */
#elif PROBE_ADIF_OPERATION == 1
 sbi ADCSRA,ADIE
#elif PROBE_ADIF_OPERATION == 2
 cbi ADCSRA,ADIE
#elif PROBE_ADIF_OPERATION == 3
 cbi ADCSRA,ADPS0           /* /64 already has ADPS0=0. */
#elif PROBE_ADIF_OPERATION == 4
 ldi r16,ADC_TRIAL_BASE
 out ADCSRA,r16             /* Known whole-byte ADIF=0 control. */
#elif PROBE_ADIF_OPERATION == 5
 ldi r16,ADC_TRIAL_BASE | (1 << ADIF)
 out ADCSRA,r16             /* Known whole-byte W1C control. */
#elif PROBE_ADIF_OPERATION == 6
 in r16,ADCSRA
 ori r16,(1 << ADIE)
 out ADCSRA,r16             /* Explicit RMW preserves read-one ADIF. */
#endif
#endif
 in r9,ADCSRA               /* Immediately after the operation/completion. */
 in r10,SREG                /* In particular, retain the actual I bit. */
 in r6,ADCL                 /* Always low THEN high; no held result lock. */
 in r7,ADCH
#if PROBE_MODE != 2
 ldi r16,RECORD_CONVERSION
#elif PROBE_ADIF_OPERATION >= 1 && PROBE_ADIF_OPERATION <= 3
 ldi r16,RECORD_ADIF_TEST
#else
 ldi r16,RECORD_ADIF_CONTROL
#endif
 mov r11,r16
 rcall probe_emit_frame     /* All observations saved before transport. */
 ldi r16,PROBE_TRIALS
 cp r2,r16
 brsh adc_probe_halt
 rjmp adc_probe_trial

adc_probe_halt:
 cli
 rjmp adc_probe_halt        /* No additional conversion or marker pulse. */

adc_probe_wait_done:
 in r18,ADCSRA
 sbrc r18,ADSC
 rjmp adc_probe_wait_done
 ret

adc_probe_recovery:
 ldi r24,lo8(8000)
 ldi r25,hi8(8000)
adc_probe_recovery_loop:
 sbiw r24,1
 brne adc_probe_recovery_loop
 ret                       /* Including call/setup: 32008 CPU clocks. */

adc_probe_unexpected_interrupt:
 cli
 rjmp adc_probe_unexpected_interrupt

#include "probe-wire.inc"
