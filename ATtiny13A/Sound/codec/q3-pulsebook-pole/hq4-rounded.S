/* Experimental extended-negative-pole EEPROM pulsebook rounded-Q3 HQ4-T1 ATtiny13A speech synthesizer.
 * Genuine 8-stage signed lattice, 7.5k PCM, 37.5kHz PWM.
 * Requires a separately retuned Q3 stream, then emit midpoint silence at 7.5 kHz.
 * CPU 9.6MHz (software CLKPR reset), PB1 OC0B output.
 */
.section .text
.global __vectors, code_end, voice_data, STACK_FLOOR
.set DDRB,0x17
.set IO_SPL,0x3d
.set SREG,0x3f
.set CLKPR,0x26
.set TCCR0A,0x2f
.set TCCR0B,0x33
.set OCR0B,0x29
.set TIMSK0,0x39
.set SAMPLE,0x60
.set READY,0x61
.set CTR,0x62
.set COEFF,0x68
.set STATE,0x70
.set STACK_FLOOR,STATE+8
.set TILT_SHIFT,1
.set VOICE_ADDR,0x1b2
.org 0x0000
__vectors:
 rjmp reset
.org 0x0006
 rjmp irq
/* Only Timer0 overflow is enabled; the other vectors may contain code. */
.org 0x0008
reset:
 cli
 clt
 ldi r16,0x9f
 out IO_SPL,r16
 ldi r16,0x80
 out CLKPR,r16
 clr r16
 out CLKPR,r16
 clr r8
 clr r11 /* independent tilt-restoration output state */
 ldi r19,5
 mov r9,r19
 ldi r28,STATE
 clr r29
 ldi r19,8
 /* r16 is still zero from CLKPR; keep the initialization byte-free. */
zero_states:
 st Y+,r16
 dec r19
 brne zero_states
 clr r5
 ldi r16,0xa7
 mov r6,r16
 ldi r30,lo8(VOICE_ADDR)
 ldi r31,hi8(VOICE_ADDR)
 rcall read_frame
 sbi DDRB,1
 ldi r16,128
 out OCR0B,r16
 ldi r16,0x23
 out TCCR0A,r16
 ldi r16,1
 out TCCR0B,r16
 ldi r16,2
 out TIMSK0,r16
 sei
wait_slot:
 tst r8
 brne wait_slot
 brtc speaking
 ldi r16,128
 mov r7,r16
 inc r8
 rjmp wait_slot
speaking:
 inc r5
 cp r5,r10
 brne current_frame
 clr r5
 rcall read_frame
current_frame:
 /* r27 is also the multiplier's zero carry-add operand in rounded mode. */
 clr r27
 tst r4
 breq noise_sample
 dec r2
 brne pulse_lag
 mov r2,r4
 clr r18
 rjmp pulse_lookup
pulse_lag:
 mov r18,r4
 sub r18,r2
 cpi r18,16
 brsh zero_excitation
pulse_lookup:
 mov r16,r22
 andi r16,48
 or r16,r18
 out 0x1e,r16
 sbi 0x1c,0
 in r23,0x1d
 /* gain<<3 <=120, so signed NEG and Q3 product are exact gain*table. */
 mov r21,r3
 lsl r21
 lsl r21
 lsl r21
 rcall mul_q3
 mov r18,r24
 rjmp filter
zero_excitation:
 clr r18
 rjmp filter
noise_sample:
 lsr r6
 brcc noise_ready
 ldi r16,0xb8
 eor r6,r16
noise_ready:
 mov r18,r3
 sbrc r6,0
 neg r18
filter:
 ldi r26,COEFF+8
 ldi r28,STATE+8
 ldi r19,8
filter_loop:
 ld r21,-Y
 ld r23,-X
 mov r20,r21
 rcall mul_q3
 sub r18,r24
 cpi r19,8
 breq skip_state_update
 mov r21,r18
 rcall mul_q3
 add r20,r24
 std Y+1,r20
skip_state_update:
 dec r19
 brne filter_loop
 st Y,r18
 /* y = s8(x + previous - (previous >> TILT_SHIFT)). */
 mov r16,r11
 .rept TILT_SHIFT
 asr r16
 .endr
 sub r11,r16
 add r18,r11
 mov r11,r18
 mov r16,r18
 subi r16,128
 mov r7,r16
 inc r8
 rjmp wait_slot
/* Signed byte * coefficient, nearest >>3 with ties toward positive infinity.
 * X high byte r27 stays zero: initialized before excitation and the lattice, X only walks
 * COEFF+8 down to COEFF, neither multiplier nor IRQ changes r27. */
mul_q3:
 cpi r23,0xf8
 breq mul_neg15
 clr r24
 clr r16
 mov r25,r23
 tst r25
 breq mul_done
 brpl mul_pos
 neg r25
 neg r21
mul_pos:
 clr r17
 sbrc r21,7
 ser r17
mul_loop:
 add r24,r21
 adc r16,r17
 dec r25
 brne mul_loop
mul_done:
.rept 3
 asr r16
 ror r24
.endr
 /* Last ROR leaves product bit 2 in C; ADC adds the half-bit rounding. */
 adc r24,r27
 ret
/* Nibble0 maps to -15/16 in this separate profile, not unstable -1.
 * floor(-15*a/16)=-a+floor(a/16); avoid signed-byte NEG of a itself. */
mul_neg15:
 mov r24,r21
 mov r16,r21
 asr r16
 asr r16
 asr r16
 asr r16
 /* Last carry is a half-unit: nearest quotient, ties toward +infinity. */
 adc r16,r27
 sub r24,r16
 neg r24
 ret
/* MiniLPC8-VBR, the ONLY supported format; updates subsets of coefficients. */
read_frame:
 lpm r16,Z+
 cpi r16,0xff
 brne vbr_pitch
 /* Keep the frozen decoder's final sample convention, then stop at wait_slot. */
 set
 ldi r30,lo8(VOICE_ADDR)
 ldi r31,hi8(VOICE_ADDR)
 lpm r16,Z+
vbr_pitch:
 mov r17,r16
 andi r16,0xc0
 mov r10,r16
 cpi r16,0xc0
 breq vbr_extended
 mov r16,r17
 andi r16,0x3f
 rjmp vbr_setpitch
vbr_extended:
 mov r16,r17
 andi r16,3
 swap r16
 lsl r16
 lsl r16
 mov r10,r16
 lpm r16,Z+
vbr_setpitch:
 mov r4,r16
 mov r2,r16
 lpm r16,Z+
 mov r22,r16
 andi r16,15
 mov r3,r16
 /* [7:6] 00=full, 01=repeat, 10=low four K, 11=high four K. */
 sbrc r22,6
 rjmp vbr_bit6
 sbrc r22,7
 rjmp vbr_low
 ldi r28,COEFF
 ldi r19,4
 rjmp vbr_read_coeffs
vbr_bit6:
 sbrs r22,7
 ret
 ldi r28,COEFF+4
 ldi r19,2
 rjmp vbr_read_coeffs
vbr_low:
 ldi r28,COEFF
 ldi r19,2
vbr_read_coeffs:
 clr r29
vbr_read_pair:
 lpm r17,Z+
 mov r16,r17
 andi r16,15
 subi r16,8
 st Y+,r16
 mov r16,r17
 swap r16
 andi r16,15
 subi r16,8
 st Y+,r16
 dec r19
 brne vbr_read_pair
 ret

irq:
 push r16
 in r16,SREG
 push r16
 dec r9
 brne irq_end
 ldi r16,5
 mov r9,r16
 tst r8
 breq irq_end
 out OCR0B,r7
 clr r8
irq_end:
 pop r16
 out SREG,r16
 pop r16
 reti
code_end:
.org VOICE_ADDR
voice_data:
.incbin "speech.hq"
.byte 0xff
