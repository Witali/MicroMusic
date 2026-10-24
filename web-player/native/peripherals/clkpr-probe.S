/* Source-only ATtiny13A CLKPR silicon probe; see clkpr-probe.md.
 * Keep the external CLKI source and OC0A capture running through the write.
 * Marker edges bracket the target instruction, not its hidden bus phase.
 */
#include "../attiny13a-registers.generated.inc"

#ifndef PROBE_PROFILE_ID
#error "Select PROBE_PROFILE_ID from clkpr-probe.json"
#endif
#ifndef PROBE_INITIAL_DIV
#define PROBE_INITIAL_DIV 0
#endif
#ifndef PROBE_FINAL_DIV
#define PROBE_FINAL_DIV 1
#endif
#ifndef PROBE_WRITE_KIND
#define PROBE_WRITE_KIND 0
#endif
#if PROBE_PROFILE_ID < 1 || PROBE_PROFILE_ID > 255
#error "Profile ID must be a nonzero byte"
#endif
#if PROBE_INITIAL_DIV < 0 || PROBE_INITIAL_DIV > 8 || PROBE_FINAL_DIV < 0 || PROBE_FINAL_DIV > 8
#error "Divider codes are exponents0..8, not physical divisors"
#endif
#if PROBE_WRITE_KIND < 0 || PROBE_WRITE_KIND > 3
#error "Write kind:0 protected,1 no-write,2 no-unlock,3 expired-unlock"
#endif

.equ PROBE_WIRE_CLOCK_BIT, PORTB2
.equ PROBE_WIRE_DATA_BIT, PORTB4
.equ PROBE_MARKER_BIT, PORTB1

.section .text
.global __vectors
__vectors:
 rjmp reset
.rept 9
 rjmp unexpected_interrupt
.endr

reset:
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
 out PRR,r16
 out TCCR0B,r16
 out TCCR0A,r16
 out ADCSRA,r16
 ldi r16,(1 << ACD)
 out ACSR,r16
 clr r16
 out PORTB,r16
 ldi r16,(1 << DDB0) | (1 << DDB1) | (1 << DDB2) | (1 << DDB4)
 out DDRB,r16                 /* PB3 remains CLKI input; PB5 remains RESET. */

 /* Establish the initial CPU divider before starting the observation clock.
  * CKSEL/SUT/CKDIV8 come from the physical fuse readback, never this OUT. */
 ldi r16,(1 << CLKPCE)
 out CLKPR,r16
 ldi r16,PROBE_INITIAL_DIV
 out CLKPR,r16
.rept 64
 nop
.endr

 /* Documented CTC observer: WGM2, OCR0A=0, CS=/1, OC0A toggle.
  * Initialize its latch in non-PWM mode using FOC, then warm up. This is not
  * the unresolved phase-correct WGM5/TOP=0 experiment. */
 ldi r16,(1 << COM0A1)
 out TCCR0A,r16
 ldi r16,(1 << FOC0A)
 out TCCR0B,r16
 clr r16
 out TCCR0B,r16
 out TCCR0A,r16
 out OCR0A,r16
 out OCR0B,r16
 out TCNT0,r16
 ldi r16,(1 << COM0A0) | (1 << WGM01)
 out TCCR0A,r16
 ldi r16,(1 << CS00)
 out TCCR0B,r16
.rept 64
 nop
.endr

 clr r2
 clr r3
 ldi r16,1
 mov r4,r16                  /* Common transport probeId1: CLKPR. */
 ldi r16,PROBE_PROFILE_ID
 mov r5,r16
 ldi r16,PROBE_WRITE_KIND
 mov r6,r16
 ldi r16,PROBE_INITIAL_DIV
 mov r7,r16
 ldi r16,PROBE_FINAL_DIV
 mov r8,r16
 rcall snapshot
 rcall probe_emit_frame      /* Sequence0: pre/boot; transport only. */

 /* No serialization or Timer0 reconfiguration inside the measured window.
  * Preloaded registers keep a marker OUT inside the protected4-cycle window. */
 ldi r16,(1 << CLKPCE)
 ldi r19,PROBE_FINAL_DIV
 ldi r20,(1 << PROBE_MARKER_BIT)
.rept 16
 nop
.endr
#if PROBE_WRITE_KIND == 0 || PROBE_WRITE_KIND == 3
 out CLKPR,r16               /* Unlock; all CLKPS/reserved bits zero. */
#else
 nop                         /* Matched no-unlock/no-write control slot. */
#endif
#if PROBE_WRITE_KIND == 3
.rept 6
 nop                         /* Deliberately beyond the4-cycle unlock window. */
.endr
#endif
 out PINB,r20                /* PB1 high immediately before target slot. */
#if PROBE_WRITE_KIND == 1
 nop                         /* No target CLKPR write. */
#else
 out CLKPR,r19               /* Accepted only for the protected profile. */
#endif
 out PINB,r20                /* PB1 low immediately after target slot. */
.rept 32
 nop
.endr
 inc r2
 rcall snapshot
 rcall probe_emit_frame      /* Sequence1: post readback; not event timing. */
finished:
 rjmp finished               /* OC0A and the external source remain running. */

snapshot:
 in r9,CLKPR
 in r10,TCCR0A
 in r11,TCCR0B
 ret

unexpected_interrupt:
 cli
 rjmp unexpected_interrupt

#include "probe-wire.inc"
