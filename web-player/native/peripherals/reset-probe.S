/* Source-only ATtiny13A physical RESET/CLKI probe. No silicon result assumed.
 * Use reset-probe.json profiles and retain the raw analog/digital capture.
 * Manufacturer symbols come from the pinned device-pack generated view. */
#include "../attiny13a-registers.generated.inc"

#ifndef PROBE_PROFILE_ID
#define PROBE_PROFILE_ID 1
#endif
#if PROBE_PROFILE_ID < 1 || PROBE_PROFILE_ID > 255
#error "PROBE_PROFILE_ID must identify a nonzero byte profile"
#endif

.equ PROBE_WIRE_CLOCK_BIT, PORTB2
.equ PROBE_WIRE_DATA_BIT, PORTB4

.section .text
.global __vectors
__vectors:
 rjmp reset
.rept 9
 rjmp unexpected_interrupt
.endr

reset:
 in r6,MCUSR                  /* First handler instruction: retain raw causes. */
 ldi r16,(1 << DDB0)
 out DDRB,r16                 /* DDR first: PB0 drives its reset PORT-low value. */
 sbi PORTB,PORTB0              /* Then drive high; never use a pull-up marker. */
 cli
 ldi r16,RAMEND
 out SPL,r16
 clr r16
 out MCUSR,r16                /* Saved r6 remains intact, including combined flags. */
 wdr
 ldi r16,(1 << WDCE) | (1 << WDE)
 out WDTCR,r16
 clr r16
 out WDTCR,r16                /* Protected disable; WDTON is unprogrammed. */
 out TIMSK0,r16
 out GIMSK,r16
 out TCCR0B,r16
 out TCCR0A,r16
 out PRR,r16
 out ADCSRA,r16
 out DIDR0,r16
 ldi r16,(1 << ACD)
 out ACSR,r16                 /* Comparator disabled; PB0/PB1 stay GPIO. */

 /* PB3 is CLKI, PB5 is RESET: neither is driven by the firmware.
  * PB0 remains high; heartbeat/trace outputs begin low. */
 ldi r16,(1 << DDB0) | (1 << DDB1) | (1 << DDB2) | (1 << DDB4)
 out DDRB,r16
 ldi r16,(1 << PORTB0)
 out PORTB,r16

 /* CLKPR and OSCCAL are observed, never written. CKDIV8 remains visible. */
 in r7,CLKPR
 in r8,OSCCAL
 in r9,DDRB
 in r10,PORTB
 clr r11                     /* kind0: boot after this reset. */
 clr r2
 clr r3                      /* Every reset starts sequence0, never retained SRAM. */
 ldi r16,2
 mov r4,r16                  /* Generic probe wire ID2: RESET/CLKI. */
 ldi r16,PROBE_PROFILE_ID
 mov r5,r16
 rcall probe_emit_frame

 /* This witness starts only after the complete boot frame. Its fixed CPU-cycle
  * loop remains stopped with CLKI and slows with CKDIV8; it is not a timebase. */
heartbeat:
 sbi PINB,PINB1               /* Documented write-one PINB toggle, PB1 only. */
 ldi r19,0
 ldi r20,1
heartbeat_delay:
 subi r19,1
 sbci r20,0
 brne heartbeat_delay
 rjmp heartbeat

unexpected_interrupt:
 cli
 rjmp unexpected_interrupt

#include "probe-wire.inc"
