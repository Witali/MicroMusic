/* Experimental MicroMusic MiniLPC-8 ATtiny13A speech synthesizer.
 * Genuine 8-stage signed lattice, 7.5k PCM, 37.5kHz PWM.
 * Compact source for a family of excitation modes.
 * CPU 9.6MHz (software CLKPR reset), PB1 OC0B output.
 */
.section .text
.global __vectors
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
.set VOICE_ADDR,0x1a0
.org 0x0000
__vectors:
 rjmp reset
.org 0x0006
 rjmp irq
.org 0x0014
reset:
 cli
 ldi r16,0x9f
 out IO_SPL,r16
 ldi r16,0x80
 out CLKPR,r16
 clr r16
 out CLKPR,r16
 sts READY,r16
 ldi r16,5
 sts CTR,r16
 ldi r28,STATE
 clr r29
 ldi r19,8
 clr r16
zero_states:
 st Y+,r16
 dec r19
 brne zero_states
 clr r5
 ldi r16,1
 mov r2,r16
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
 lds r16,READY
 tst r16
 brne wait_slot
 inc r5
 brne current_frame
 rcall read_frame
current_frame:
 tst r4
 breq noise_sample
 dec r2
 breq new_pulse
 mov r18,r4
 sub r18,r2
 cpi r18,1
 breq pulse_second
 cpi r18,2
 breq pulse_third
 cpi r18,3
 breq pulse_fourth
 clr r18
 rjmp filter
pulse_second:
 mov r18,r3
 lsl r18
 add r18,r3
 rjmp filter
pulse_third:
 mov r18,r3
 lsl r18
 rjmp filter
pulse_fourth:
 mov r18,r3
 neg r18
 rjmp filter

new_pulse:
 mov r2,r4
 mov r18,r3
 lsl r18
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
 clr r27
 ldi r28,STATE+8
 clr r29
 ldi r19,8
filter_loop:
 ld r21,-Y
 ld r23,-X
 mov r20,r21
 rcall mul_q4
 sub r18,r24
 cpi r19,8
 breq skip_state_update
 mov r21,r18
 rcall mul_q4
 add r20,r24
 std Y+1,r20
skip_state_update:
 dec r19
 brne filter_loop
 st Y,r18
 mov r16,r18
 subi r16,128
 sts SAMPLE,r16
 ldi r16,1
 sts READY,r16
 rjmp wait_slot
/* signed 8-bit sample * coefficient (signed -7..7), arithmetic >>4 */
mul_q4:
 clr r24
 clr r0
 mov r25,r23
 tst r25
 breq mul_done
 brpl mul_pos
 neg r25
 neg r21
mul_pos:
 mov r16,r21
 clr r17
 sbrc r16,7
 ser r17
 sbrs r25,0
 rjmp mult_skip1
 add r24,r16
 adc r0,r17
mult_skip1:
 lsl r16
 rol r17
 sbrs r25,1
 rjmp mult_skip2
 add r24,r16
 adc r0,r17
mult_skip2:
 lsl r16
 rol r17
 sbrs r25,2
 rjmp mult_skip3
 add r24,r16
 adc r0,r17
mult_skip3:
mul_done:
 asr r0
 ror r24
 asr r0
 ror r24
 asr r0
 ror r24
 asr r0
 ror r24
 ret
/* Full frame: 1 byte pitch (0 means unvoiced), 1 byte gain, four packed coefficient bytes.
 * Each signed k = nibble - 8. Decoding loops after 256 audio samples.
 */
read_frame:
 lpm r16,Z+
 cpi r16,0xff
 brne read_pitch
 ldi r30,lo8(VOICE_ADDR)
 ldi r31,hi8(VOICE_ADDR)
 lpm r16,Z+
read_pitch:
 mov r24,r16
 andi r16,0x7f
 mov r4,r16
 mov r2,r16
 lpm r3,Z+
 sbrc r24,7
 ret
 ldi r28,COEFF
 clr r29
 ldi r19,4
read_k:
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
 brne read_k
 ret
irq:
 push r16
 in r16,SREG
 push r16
 push r17
 lds r16,CTR
 dec r16
 brne irq_end
 ldi r16,5
 lds r17,READY
 tst r17
 breq irq_end
 lds r17,SAMPLE
 out OCR0B,r17
 clr r17
 sts READY,r17
irq_end:
 sts CTR,r16
 pop r17
 pop r16
 out SREG,r16
 pop r16
 reti
code_end:
.org VOICE_ADDR
voice_data:
.incbin "voice_tinylpc.bin"
.byte 0xff
