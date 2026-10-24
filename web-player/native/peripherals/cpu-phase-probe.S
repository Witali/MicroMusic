/* Physical acquisition firmware; reset/GPR observations are never assumed.
 * Generated common CPU symbols precede the unmodified official C header.
 * Numeric SFR adaptation keeps vendor register operands valid in assembly. */
#include "../attiny13a-registers.generated.inc"
#define _AVR_IO_H_ 1
#define _SFR_IO8(address) (address)
#define _SFR_IO16(address) (address)
#include "../../vendor/microchip/ATtiny_DFP/3.4.278/include/avr/iotn13a.h"
#ifndef PROBE_PROFILE_ID
#define PROBE_PROFILE_ID 0
#endif
#if PROBE_PROFILE_ID < 0 || PROBE_PROFILE_ID > 21
#error "Select a CPU phase profile0..21 from cpu-phase-probe.json"
#endif

.equ TEST_BASE,RAMSTART+16
.equ TEST_MAGIC,RAMSTART+20
.equ SNAP_BASE,RAMSTART+32
.equ PROBE_WIRE_CLOCK_BIT,PORTB2
.equ PROBE_WIRE_DATA_BIT,PORTB4

.section .text
.global __vectors,reset,phase_prelude,phase_marker,phase_target,after_target
.global call_target,irq_handler,flash_data,TEST_BASE,TEST_MAGIC,SNAP_BASE
__vectors:
 rjmp reset
 rjmp irq_handler
.rept 8
 rjmp unexpected_interrupt
.endr
reset:
 in r6,MCUSR
 /* STS does not alter these source GPRs. Snapshot before any setup/serializer. */
 sts SNAP_BASE+0,r0
 sts SNAP_BASE+1,r20
 sts SNAP_BASE+2,r26
 sts SNAP_BASE+3,r27
 sts SNAP_BASE+4,r30
 sts SNAP_BASE+5,r31
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
 out TCCR0B,r16
 out TCCR0A,r16
 out ADCSRA,r16
 out DIDR0,r16
 out PORTB,r16
 ldi r16,(1 << ACD)
 out ACSR,r16
 ldi r16,(1 << DDB0) | (1 << DDB2) | (1 << DDB4)
 out DDRB,r16                 /* 0x15: PB1 ARM, PB3 CLKI, PB5 RESET stay inputs. */
 clr r2
 clr r3
 ldi r16,4
 mov r4,r16
 ldi r16,PROBE_PROFILE_ID
 mov r5,r16
 /* Boot0 precedes any test-memory/tag initialization. */
 lds r7,TEST_MAGIC
 lds r8,TEST_BASE+0
 lds r9,TEST_BASE+1
 lds r10,TEST_BASE+2
 lds r11,TEST_BASE+3
 rcall probe_emit_frame
 inc r2
 lds r6,SNAP_BASE+0
 lds r7,SNAP_BASE+1
 lds r8,SNAP_BASE+2
 lds r9,SNAP_BASE+3
 lds r10,SNAP_BASE+4
 lds r11,SNAP_BASE+5
 rcall probe_emit_frame       /* Boot1: raw old r0,r20,Xlo,Xhi,Zlo,Zhi. */
arm_low:
 sbic PINB,PINB1
 rjmp arm_low
#if PROBE_PROFILE_ID == 7
 ldi r16,(1 << ISC01) | (1 << ISC00)
 out MCUCR,r16
 ldi r16,(1 << INTF0)
 out GIFR,r16
 ldi r16,(1 << INT0)
 out GIMSK,r16               /* ARM rising can set a real pending INT0, I still0. */
#endif
arm_high:
 sbis PINB,PINB1
 rjmp arm_high
 ldi r16,0x11
 sts TEST_BASE+0,r16
 ldi r16,0x22
 sts TEST_BASE+1,r16
 ldi r16,0x33
 sts TEST_BASE+2,r16
 ldi r16,0x44
 sts TEST_BASE+3,r16
 ldi r16,0x55
 mov r0,r16
 ldi r20,0xe7
 ldi r26,lo8(TEST_BASE+1)
 ldi r27,hi8(TEST_BASE+1)
#if PROBE_PROFILE_ID == 17
 ldi r30,lo8(flash_data+1)     /* Odd-byte LPM control observes0x36. */
 ldi r31,hi8(flash_data+1)
#else
 ldi r30,lo8(flash_data)       /* Even byte0xa9; Z+ advances toward0x36. */
 ldi r31,hi8(flash_data)
#endif
#if PROBE_PROFILE_ID == 1 || PROBE_PROFILE_ID == 3 || PROBE_PROFILE_ID == 4 || PROBE_PROFILE_ID == 7
 ldi r16,TEST_BASE+1
 out SPL,r16
#elif PROBE_PROFILE_ID == 2
 ldi r16,TEST_BASE
 out SPL,r16
#elif PROBE_PROFILE_ID == 5 || PROBE_PROFILE_ID == 6
 ldi r16,hi8(pm(after_target))
 sts TEST_BASE+0,r16
 ldi r16,lo8(pm(after_target))
 sts TEST_BASE+1,r16
 ldi r16,TEST_BASE-1
 out SPL,r16
#endif
#if PROBE_PROFILE_ID == 4
 ldi r30,lo8(pm(call_target))
 ldi r31,hi8(pm(call_target))
#endif
 ldi r16,0xa5
 sts TEST_MAGIC,r16           /* Tag written last, only after fresh ARM. */
 ldi r16,(1 << PORTB0)
 clr r21
 rjmp phase_prelude

/* Target word255 exercises a two-byte return address crossing the low byte.
 * The verifier reads symbols from ELF; it never supplies a guessed callee PC. */
.org 506
phase_prelude:
#if PROBE_PROFILE_ID == 7
 sei
#else
 nop
#endif
phase_marker:
 out PORTB,r16               /* Word254: driven PB0 high, target starts next. */
phase_target:
#if PROBE_PROFILE_ID == 0 || PROBE_PROFILE_ID == 7
 nop
#elif PROBE_PROFILE_ID == 1
 push r20
#elif PROBE_PROFILE_ID == 2
 pop r20
#elif PROBE_PROFILE_ID == 3
 rcall call_target
#elif PROBE_PROFILE_ID == 4
 icall
#elif PROBE_PROFILE_ID == 5
 ret
#elif PROBE_PROFILE_ID == 6
 reti
#elif PROBE_PROFILE_ID == 8
 ld r20,X
#elif PROBE_PROFILE_ID == 9
 ld r20,X+
#elif PROBE_PROFILE_ID == 10
 ld r20,-X
#elif PROBE_PROFILE_ID == 11
 st X,r20
#elif PROBE_PROFILE_ID == 12
 st X+,r20
#elif PROBE_PROFILE_ID == 13
 st -X,r20
#elif PROBE_PROFILE_ID == 14
 lds r20,TEST_BASE+1
#elif PROBE_PROFILE_ID == 15
 sts TEST_BASE+1,r20
#elif PROBE_PROFILE_ID == 16
 lpm
#elif PROBE_PROFILE_ID == 17
 lpm r20,Z
#elif PROBE_PROFILE_ID == 18
 lpm r20,Z+
#elif PROBE_PROFILE_ID == 19
 in r20,PINB
#elif PROBE_PROFILE_ID == 20
 sbis PINB,PINB1
 sts TEST_BASE+2,r20
#elif PROBE_PROFILE_ID == 21
 sbic PINB,PINB1
 sts TEST_BASE+2,r20
#endif
after_target:
 out PORTB,r21
 rjmp complete
call_target:
 out PORTB,r21               /* Bracket call3+OUT1; do not serialize on test SP. */
 ret
irq_handler:
 out PORTB,r21               /* Real IRQ entry4 + vector RJMP2 + OUT1. */
 reti
complete:
 sts SNAP_BASE+6,r0
 sts SNAP_BASE+7,r20
 sts SNAP_BASE+8,r26
 sts SNAP_BASE+9,r27
 sts SNAP_BASE+10,r30
 sts SNAP_BASE+11,r31
 cli
 ldi r16,RAMEND
 out SPL,r16                 /* Restore encoder stack before any RCALL. */
 ldi r16,2
 mov r2,r16
 clr r3
 ldi r16,0
 mov r6,r16                  /* Completion0 uses the boot memory layout; no cause. */
 lds r7,TEST_MAGIC
 lds r8,TEST_BASE+0
 lds r9,TEST_BASE+1
 lds r10,TEST_BASE+2
 lds r11,TEST_BASE+3
 rcall probe_emit_frame
 inc r2
 lds r6,SNAP_BASE+6
 lds r7,SNAP_BASE+7
 lds r8,SNAP_BASE+8
 lds r9,SNAP_BASE+9
 lds r10,SNAP_BASE+10
 lds r11,SNAP_BASE+11
 rcall probe_emit_frame
finished:
 rjmp finished
unexpected_interrupt:
 cli
 rjmp unexpected_interrupt
#include "probe-wire.inc"
.balign 2
flash_data:
 .byte 0xa9,0x36
