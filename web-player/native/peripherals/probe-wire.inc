/* Project-owned source-only measurement transport, wire version2.
 * Caller includes the official attiny13a-registers.generated.inc first and
 * defines PROBE_WIRE_CLOCK_BIT / PROBE_WIRE_DATA_BIT (PORTB bit positions).
 * Outputs must already be driven; trace clock starts and finishes low.
 * Payload: 2, r4(probe), r5(profile), r2:r3(sequence LE), r6..r11(raw data).
 * Packet: a5 5a, eleven payload bytes, XOR of those eleven bytes (14 total).
 * Clobbers r12, r17, r18 and SREG; all other registers are preserved.
 * Main→emit→byte uses at most two return addresses/four stack bytes.
 * Serialization is after the measurement; its times are not event times.
 */
.if PROBE_WIRE_CLOCK_BIT < 0 || PROBE_WIRE_CLOCK_BIT > 5
.error "Trace clock must be a Port B bit"
.endif
.if PROBE_WIRE_DATA_BIT < 0 || PROBE_WIRE_DATA_BIT > 5
.error "Trace data must be a Port B bit"
.endif
.if PROBE_WIRE_CLOCK_BIT == PROBE_WIRE_DATA_BIT
.error "Trace clock and data must use distinct pins"
.endif

probe_emit_frame:
 ldi r17,0xa5
 rcall probe_wire_byte
 ldi r17,0x5a
 rcall probe_wire_byte
 clr r12
 ldi r17,2
 rcall probe_wire_checked
 mov r17,r4
 rcall probe_wire_checked
 mov r17,r5
 rcall probe_wire_checked
 mov r17,r2
 rcall probe_wire_checked
 mov r17,r3
 rcall probe_wire_checked
 mov r17,r6
 rcall probe_wire_checked
 mov r17,r7
 rcall probe_wire_checked
 mov r17,r8
 rcall probe_wire_checked
 mov r17,r9
 rcall probe_wire_checked
 mov r17,r10
 rcall probe_wire_checked
 mov r17,r11
 rcall probe_wire_checked
 mov r17,r12
 rcall probe_wire_byte
 ret
probe_wire_checked:
 eor r12,r17
 rjmp probe_wire_byte
probe_wire_byte:
 ldi r18,8
probe_wire_bit:
 cbi PORTB,PROBE_WIRE_DATA_BIT
 sbrc r17,7
 sbi PORTB,PROBE_WIRE_DATA_BIT
 nop
 sbi PORTB,PROBE_WIRE_CLOCK_BIT
 nop
 cbi PORTB,PROBE_WIRE_CLOCK_BIT
 lsl r17
 dec r18
 brne probe_wire_bit
 ret
