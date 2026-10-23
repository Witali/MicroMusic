/* Three-tone EEPROM bell prelude and one-shot HQ4 voice.
 * Signed eight-stage lattice, 7.5k PCM, 37.5kHz PWM.
 * The complete bell-plus-voice stream ends in midpoint silence.
 * CPU 9.6MHz (software CLKPR reset), PB1 OC0B output.
 */
.include "config.inc"
.section .text
.global __vectors, code_end, voice_data, bell_data, STACK_FLOOR
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
.set VOICE_ADDR,voice_data
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
 ldi r19,5
 mov r9,r19
 ldi r28,COEFF
 clr r29
 ldi r30,lo8(bell_data)
 ldi r31,hi8(bell_data)
 ldi r19,15
bell_initialize:
 lpm r16,Z+
 st Y+,r16
 dec r19
 brne bell_initialize
 ldi r16,64
 mov r14,r16
 ldi r16,BELL_BLOCKS
 mov r15,r16
 ldi r16,MUTE_BLOCKS
 mov r11,r16
 clr r12
 ldi r16,DECAY_BLOCKS
 mov r13,r16
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
 tst r15
 breq after_bell
 rjmp bell_sample
after_bell:
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
 sbrc r22,4
 sub r18,r3
 rjmp filter
pulse_third:
 mov r18,r3
 lsl r18
 sbrc r22,5
 sub r18,r3
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
output_sample:
 mov r16,r18
 subi r16,128
 mov r7,r16
 inc r8
 rjmp wait_slot
/* Three independent 16-bit tonal oscillators. All descriptor storage is
 * shared with HQ4 coefficient/state RAM; the voice initializes it afterwards.
 */
bell_sample:
 clr r18
 tst r11
 brne bell_count
 ldi r26,COEFF
 clr r27
 ldi r28,COEFF+6
 clr r29
 ldi r30,COEFF+12
 clr r31
 ldi r19,3
bell_oscillator:
 ld r20,X+
 ld r21,X+
 ld r16,Y+
 add r20,r16
 ld r16,Y+
 adc r21,r16
 st -X,r21
 st -X,r20
 subi r26,-2
 mov r16,r21
 lsr r16
 lsr r16
 out 0x1e,r16
 sbi 0x1c,0
 in r21,0x1d
 ld r23,Z+
 rcall mul_q4
 add r18,r24
 dec r19
 brne bell_oscillator
 subi r18,-1
 mov r16,r12
bell_shift:
 tst r16
 breq bell_count
 asr r18
 dec r16
 rjmp bell_shift
bell_count:
 dec r14
 brne bell_output
 ldi r16,64
 mov r14,r16
 dec r15
 breq bell_voice
 tst r11
 breq bell_decay
 dec r11
 rjmp bell_output
bell_decay:
 dec r13
 brne bell_output
 inc r12
 ldi r16,DECAY_BLOCKS
 mov r13,r16
 rjmp bell_output
bell_voice:
 rcall start_voice
bell_output:
 rjmp output_sample
start_voice:
 ldi r28,STATE
 clr r29
 ldi r19,8
 clr r16
voice_zero_states:
 st Y+,r16
 dec r19
 brne voice_zero_states
 clr r5
 ldi r16,0xa7
 mov r6,r16
 ldi r30,lo8(VOICE_ADDR)
 ldi r31,hi8(VOICE_ADDR)
 rjmp read_frame
/* signed 8-bit sample * coefficient (signed -7..7), arithmetic >>4 */
mul_q4:
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
 swap r16
 andi r16,0xf0
 swap r24
 andi r24,0x0f
 or r24,r16
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
bell_data:
.incbin "bell.bin"
voice_data:
.incbin "speech.hq"
.byte 0xff
