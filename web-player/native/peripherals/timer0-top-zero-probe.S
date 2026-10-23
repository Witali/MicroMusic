/* ATtiny13A source-only silicon probe. See timer0-top-zero-probe.md.
 * Build with avr-gcc -mmcu=attiny13a -nostdlib -nostartfiles.
 * Do not infer the WGM5/TOP=0 result from this firmware: it only records it.
 */
#ifndef PROBE_MODE
#define PROBE_MODE 5
#endif
#ifndef PROBE_INITIAL_TOP
#define PROBE_INITIAL_TOP 0
#endif
#ifndef PROBE_OCR0B
#define PROBE_OCR0B 0
#endif
#ifndef PROBE_COM0A
#define PROBE_COM0A 1
#endif
#ifndef PROBE_COM0B
#define PROBE_COM0B 2
#endif
#ifndef PROBE_INITIAL_LEVELS
#define PROBE_INITIAL_LEVELS 0
#endif
#ifndef PROBE_WRITE_AFTER
#define PROBE_WRITE_AFTER 0
#endif
#ifndef PROBE_NEW_TOP
#define PROBE_NEW_TOP 0
#endif
#ifndef PROBE_WRITE_TCNT
#define PROBE_WRITE_TCNT 0
#endif
#ifndef PROBE_INITIAL_COUNTER
#define PROBE_INITIAL_COUNTER 0
#endif

#if PROBE_MODE != 1 && PROBE_MODE != 5
#error "This probe supports only the two phase-correct modes"
#endif
#if PROBE_COM0A < 0 || PROBE_COM0A > 3 || PROBE_COM0B < 0 || PROBE_COM0B > 3 || PROBE_COM0B == 1
#error "Invalid/reserved compare output mode"
#endif
#if PROBE_INITIAL_TOP < 0 || PROBE_INITIAL_TOP > 255 || PROBE_OCR0B < 0 || PROBE_OCR0B > 255
#error "Compare register value out of range"
#endif
#if PROBE_NEW_TOP < 0 || PROBE_NEW_TOP > 255 || PROBE_WRITE_AFTER < 0 || PROBE_WRITE_AFTER > 255
#error "Scheduled write value/index out of range"
#endif
#if PROBE_INITIAL_COUNTER < 0 || PROBE_INITIAL_COUNTER > 255 || PROBE_INITIAL_LEVELS < 0 || PROBE_INITIAL_LEVELS > 3
#error "Initial counter/latch value out of range"
#endif

/* I/O offsets from DS40002307A section20. No copied device header required. */
.equ PINB_IO,   0x16
.equ DDRB_IO,   0x17
.equ PORTB_IO,  0x18
.equ WDTCR_IO,  0x21
.equ PRR_IO,    0x25
.equ CLKPR_IO,  0x26
.equ OCR0B_IO,  0x29
.equ TCCR0A_IO, 0x2f
.equ TCNT0_IO,  0x32
.equ TCCR0B_IO, 0x33
.equ MCUSR_IO,  0x34
.equ OCR0A_IO,  0x36
.equ TIFR0_IO,  0x38
.equ TIMSK0_IO, 0x39
.equ GIMSK_IO,  0x3b
.equ SPL_IO,    0x3d

.section .text
.global __vectors
__vectors:
 rjmp reset
.rept 9
 rjmp unexpected_interrupt
.endr

reset:
 cli
 ldi r16,0x9f
 out SPL_IO,r16
 clr r16
 out MCUSR_IO,r16
 wdr
 ldi r16,0x18
 out WDTCR_IO,r16
 clr r16
 out WDTCR_IO,r16
 out TIMSK0_IO,r16
 out GIMSK_IO,r16
 out PRR_IO,r16
 out TCCR0B_IO,r16
 out TCCR0A_IO,r16
 out 0x06,r16                 /* ADC disabled. */
 ldi r16,0x80
 out 0x08,r16                 /* Comparator disabled; PB0/PB1 remain digital. */
 out CLKPR_IO,r16
 clr r16
 out CLKPR_IO,r16             /* /1, then settle before accepting T0 pulses. */
 out PORTB_IO,r16
 ldi r16,0x0f
 out DDRB_IO,r16              /* OC0A, OC0B, trace clock, trace data outputs. */

 /* Establish OC latches with the documented non-PWM FOC mechanism. */
 ldi r16,((2 | (PROBE_INITIAL_LEVELS & 1)) << 6) | ((2 | ((PROBE_INITIAL_LEVELS >> 1) & 1)) << 4)
 out TCCR0A_IO,r16
 ldi r16,0xc0
 out TCCR0B_IO,r16
 clr r16
 out TCCR0A_IO,r16
 out TCCR0B_IO,r16

 /* Write OCR while buffering is disabled. TCNT0 is left at its reset value
  * by default, so the first pulse does NOT acquire write-induced blocking. */
 ldi r16,PROBE_INITIAL_TOP
 out OCR0A_IO,r16
 ldi r16,PROBE_OCR0B
 out OCR0B_IO,r16
#if PROBE_WRITE_TCNT
 ldi r16,PROBE_INITIAL_COUNTER
 out TCNT0_IO,r16
#endif
 ldi r16,(PROBE_COM0A << 6) | (PROBE_COM0B << 4) | 1
 out TCCR0A_IO,r16
 ldi r16,((PROBE_MODE & 4) << 1) | 7
 out TCCR0B_IO,r16            /* Rising external T0; no timer clock without input. */
 ldi r16,0x0e
 out TIFR0_IO,r16
 clr r2                      /* External rising-edge sequence, modulo65536. */
 clr r3
 clr r13
#if PROBE_WRITE_AFTER
 ldi r16,1
 mov r13,r16                 /* One scheduled write, never repeated on wrap. */
#endif
 .rept 64
 nop
 .endr
 clr r4                      /* Boot/configuration record, sequence0. */
 rcall snapshot
 rcall emit_frame

wait_high:
 sbis PINB_IO,4
 rjmp wait_high
 /* PINB synchronization precedes T0 edge detection.32 CPU periods exceed
  * the documented2.5..3.5-period T0 latency without assuming its exact phase. */
 .rept 32
 nop
 .endr
 inc r2
 brne sequence_ready
 inc r3
sequence_ready:
 ldi r16,1
 mov r4,r16
 rcall snapshot
 rcall emit_frame
#if PROBE_WRITE_AFTER
 tst r13
 breq wait_low
 tst r3
 brne wait_low
 ldi r16,PROBE_WRITE_AFTER
 cp r2,r16
 brne wait_low
 clr r13
 ldi r16,PROBE_NEW_TOP
 out OCR0A_IO,r16             /* Between pulses: record buffered write readback. */
 ldi r16,2
 mov r4,r16
 rcall snapshot
 rcall emit_frame
#endif
wait_low:
 sbic PINB_IO,4
 rjmp wait_low
 rjmp wait_high

snapshot:
 in r5,TCNT0_IO
 in r6,TIFR0_IO
 in r7,PINB_IO
 in r8,OCR0A_IO
 in r9,OCR0B_IO
 in r10,TCCR0A_IO
 in r11,TCCR0B_IO
 ldi r16,0x0e
 out TIFR0_IO,r16             /* W1C only AFTER saving all raw observations. */
 ret

emit_frame:
 ldi r17,0xa5
 rcall send_byte
 ldi r17,0x5a
 rcall send_byte
 clr r12
 ldi r17,1                   /* Wire-format version. */
 rcall checked_byte
 mov r17,r4                  /* Type0 boot,1 sampled pulse,2 OCR write. */
 rcall checked_byte
 mov r17,r2
 rcall checked_byte
 mov r17,r3
 rcall checked_byte
 mov r17,r5
 rcall checked_byte
 mov r17,r6
 rcall checked_byte
 mov r17,r7
 rcall checked_byte
 mov r17,r8
 rcall checked_byte
 mov r17,r9
 rcall checked_byte
 mov r17,r10
 rcall checked_byte
 mov r17,r11
 rcall checked_byte
 mov r17,r12
 rcall send_byte
 ret
checked_byte:
 eor r12,r17
 rjmp send_byte
send_byte:
 ldi r18,8
send_bit:
 cbi PORTB_IO,3
 sbrc r17,7
 sbi PORTB_IO,3
 nop
 sbi PORTB_IO,2               /* Capture data on this rising trace-clock edge. */
 nop
 cbi PORTB_IO,2
 lsl r17
 dec r18
 brne send_bit
 ret

unexpected_interrupt:
 cli
 rjmp unexpected_interrupt
