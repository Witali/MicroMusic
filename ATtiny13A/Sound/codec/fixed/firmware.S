/* Exact period-fixed-v1 synthesis. ATtiny13A, 9.6 MHz, PB1 PWM 37.5 kHz.
 * A DAC sample is emitted every five timer overflows (7500 Hz).
 * No hardware MUL. Word-immediate arithmetic is supported by this core.
 */
.include "config.inc"
.section .text
.global __vectors, decoder_end, wave_data, noise_data, field_data
.set HIST,0x68
.set BITBUF,0x60
.set DCLO,0x61
.set DCHI,0x62
.global STACK_FLOOR
.set STACK_FLOOR,HIST+HISTORY_LENGTH
.org 0
__vectors:
 rjmp reset
.org 6
 rjmp irq
.org 0x14
reset:
 cli
 clr r0
 ldi r16,0x9f
 out 0x3d,r16
 ldi r16,0x80
 out 0x26,r16
 out 0x26,r0
 sts DCLO,r0
 sts DCHI,r0
 clr r8
 ldi r16,5
 mov r9,r16
 rcall restart
 sbi 0x17,1
 ldi r16,128
 out 0x29,r16
 ldi r16,0x23
 out 0x2f,r16
 ldi r16,1
 out 0x33,r16
 ldi r16,2
 out 0x39,r16
 sei
wait:
 tst r8
 brne wait
 /* Shift the white-noise history; the last zero tap needs a 16th byte. */
.if ENABLE_FIR
 ldi r28,HIST+14
 clr r29
 ldi r22,14
history_loop:
 ld r16,-Y
 std Y+1,r16
 dec r22
 brne history_loop
.else
 lds r16,HIST
 sts HIST+1,r16
.endif
 ldi r22,8
random_loop:
 lsr r13
 ror r12
 brcc random_skip
 ldi r16,0xb4
 eor r13,r16
random_skip:
 dec r22
 brne random_loop
 mov r16,r12
 subi r16,128
 sts HIST,r16
 mov r16,r2
 mov r17,r3
 rcall render
 push r24
 mov r16,r4
 mov r17,r5
 rcall render
 pop r20
 /* Signed (new-old)*time, rounded >>6, then old. */
 mov r18,r24
 clr r19
 sbrc r18,7
 ser r19
 clr r21
 sbrc r20,7
 ser r21
 sub r18,r20
 sbc r19,r21
 mov r22,r1
 rcall multiply
 adiw r24,32
 lsl r24
 rol r25
 lsl r24
 rol r25
 add r25,r20
 mov r24,r25
.if DC_SHIFT
 /* The integrator is never reset by a phrase loop. */
 lds r18,DCLO
 lds r19,DCHI
 mov r16,r18
 mov r17,r19
 subi r16,-(1 << (DC_SHIFT-1))
 sbci r17,-1
 .rept (8-DC_SHIFT)
 lsl r16
 rol r17
 .endr
 clr r25
 sbrc r24,7
 ser r25
 clr r16
 sbrc r17,7
 ser r16
 sub r24,r17
 sbc r25,r16
 add r18,r24
 adc r19,r25
 sts DCLO,r18
 sts DCHI,r19
 rcall saturate
.endif
 subi r24,128
 mov r7,r24
 inc r8
 /* Phase pitch changes at block starts, fade frames at block centers. */
 mov r16,r6
 mov r17,r6
 swap r16
 lsl r16
 andi r16,0xe0
 lsr r17
 lsr r17
 lsr r17
 add r10,r16
 adc r11,r17
 inc r1
 mov r16,r1
 andi r16,63
 mov r1,r16
 breq center
 cpi r16,32
 breq block_boundary
 rjmp wait
block_boundary:
 mov r6,r14
 dec r15
 breq phrase_end
 rjmp wait
phrase_end:
 rcall restart
 rjmp wait
center:
 mov r2,r4
 mov r3,r5
 ldi r16,1
 cp r15,r16
 brne next_frame
 rjmp wait
next_frame:
 rcall read_frame
 rjmp wait

restart:
 ldi r28,HIST
 clr r29
 ldi r22,HISTORY_LENGTH
clear_history:
 st Y+,r0
 dec r22
 brne clear_history
 ldi r16,lo8(INITIAL_PHASE)
 mov r10,r16
 ldi r16,hi8(INITIAL_PHASE)
 mov r11,r16
 ldi r16,lo8(NOISE_SEED)
 mov r12,r16
 ldi r16,hi8(NOISE_SEED)
 mov r13,r16
 ldi r26,lo8(field_data)
 ldi r27,hi8(field_data)
 ldi r16,1
 sts BITBUF,r16
 clr r4
 clr r5
 clr r14
 rcall read_frame
 mov r2,r4
 mov r3,r5
 mov r6,r14
 ldi r16,BLOCKS
 mov r15,r16
 ldi r16,32
 mov r1,r16
 ret

/* r18:r19 signed multiplicand, r22 unsigned multiplier, r24:r25 output. */
multiply:
 clr r24
 clr r25
multiply_loop:
 lsr r22
 brcc multiply_skip
 add r24,r18
 adc r25,r19
multiply_skip:
 lsl r18
 rol r19
 tst r22
 brne multiply_loop
 ret

/* r16 header, r17 residual; signed int8 output in r24. */
render:
 push r17
 mov r20,r16
 andi r16,0x70
 breq base_zero
.if ENABLE_UNVOICED
 sbrs r20,7
 rjmp base_noise
.endif
 /* Packed 4-bit wave lookup, with wrapping inside each 32-tap word. */
 mov r30,r20
 andi r30,15
 swap r30
 mov r16,r11
 swap r16
 andi r16,15
 or r30,r16
 ldi r31,0
 subi r30,lo8(-(wave_data))
 sbci r31,hi8(-(wave_data))
 lpm r16,Z
 sbrc r11,3
 rjmp wave_odd
 mov r18,r16
 andi r18,15
 swap r16
 andi r16,15
 rjmp wave_pair
wave_odd:
 mov r18,r16
 swap r18
 andi r18,15
 mov r30,r11
 swap r30
 andi r30,15
 inc r30
 andi r30,15
 mov r16,r20
 andi r16,15
 swap r16
 or r30,r16
 clr r31
 subi r30,lo8(-(wave_data))
 sbci r31,hi8(-(wave_data))
 lpm r16,Z
 andi r16,15
wave_pair:
 mov r21,r18
 sub r16,r18
 mov r18,r16
 clr r19
 sbrc r18,7
 ser r19
 mov r22,r11
 andi r22,7
 mov r16,r10
 lsl r16
 rol r22
 rcall multiply
 swap r21
 andi r21,0xf0
 add r24,r21
 subi r24,128
 clr r25
 sbrc r24,7
 ser r25
 rjmp base_gain
.if ENABLE_UNVOICED
base_noise:
 rcall high_noise
 rjmp base_gain
.endif
base_zero:
 clr r24
 clr r25
 rjmp residual
base_gain:
 mov r22,r20
 swap r22
 andi r22,7
 cpi r22,7
 breq residual
 cpi r22,6
 breq gain_three_quarters
 ldi r16,6
 sub r16,r22
 mov r22,r16
gain_shift:
 asr r25
 ror r24
 dec r22
 brne gain_shift
 /* The final discarded bit rounds once, with ties toward positive infinity.
  * DEC/BRNE preserve carry; ADC also propagates a low-byte overflow. */
 adc r24,r0
 adc r25,r0
 rjmp residual
gain_three_quarters:
 mov r18,r24
 mov r19,r25
 lsl r24
 rol r25
 add r24,r18
 adc r25,r19
 ldi r22,2
 rjmp gain_shift
residual:
 pop r17
 mov r22,r17
 andi r22,15
 breq saturate
 push r24
 push r25
.if ENABLE_FIR
 push r17
 swap r17
 andi r17,3
 breq residual_white
 rcall colored_noise
 rjmp residual_multiply
residual_white:
 rcall high_noise
residual_multiply:
 pop r17
.else
 rcall high_noise
.endif
 mov r22,r17
 andi r22,15
 mov r18,r24
 mov r19,r25
 rcall multiply
.if ENABLE_FIR
 andi r17,0x30
 breq residual_white_scale
 asr r25
 ror r24
 asr r25
 ror r24
 mov r18,r24
 mov r19,r25
 lsl r24
 rol r25
 add r24,r18
 adc r25,r19
 subi r24,128
 sbci r25,-1
 mov r24,r25
 rjmp residual_add
.endif
residual_white_scale:
 adiw r24,32
 lsl r24
 rol r25
 lsl r24
 rol r25
 mov r24,r25
residual_add:
 clr r25
 sbrc r24,7
 ser r25
 pop r19
 pop r18
 add r24,r18
 adc r25,r19
saturate:
 clr r16
 sbrc r24,7
 ser r16
 cp r16,r25
 breq saturation_done
 ldi r24,127
 sbrc r25,7
 ldi r24,128
saturation_done:
 ret

high_noise:
 lds r24,HIST
 lds r18,HIST+1
 clr r25
 sbrc r24,7
 ser r25
 clr r19
 sbrc r18,7
 ser r19
 sub r24,r18
 sbc r25,r19
 ret

/* r17 color1..3. Signed FIR, all intermediate bounds checked by exporter. */
.if ENABLE_FIR
colored_noise:
.if SINGLE_FIR
 ldi r30,lo8(noise_data)
 ldi r31,hi8(noise_data)
.else
 dec r17
 lsl r17
 lsl r17
 lsl r17
 mov r30,r17
 clr r31
 subi r30,lo8(-(noise_data))
 sbci r31,hi8(-(noise_data))
.endif
 ldi r28,HIST
 clr r29
 ldi r23,8
 clr r24
 clr r25
fir_pair:
 lpm r20,Z+
 ld r18,Y+
 rcall fir_tap
 swap r20
 ld r18,Y+
 rcall fir_tap
 dec r23
 brne fir_pair
 ret
fir_tap:
 mov r22,r20
 andi r22,15
 breq fir_done
 clr r19
 sbrc r18,7
 ser r19
 sbrs r22,3
 rjmp fir_add
 neg r22
 andi r22,15
 com r19
 neg r18
 sbci r19,255
fir_add:
 add r24,r18
 adc r25,r19
 dec r22
 brne fir_add
fir_done:
 ret
.endif

/* Compact sequential parameter reader. X persists between reads. */
read_frame:
 lds r17,BITBUF
 rcall read_bit
 brcc read_gain
 rcall read_bit
 brcs pitch_medium
 rcall read_bit
 ldi r16,1
 brcc pitch_add
 ldi r16,255
 rjmp pitch_add
pitch_medium:
 rcall read_bit
 brcs pitch_literal
 ldi r22,3
 rcall read_bits
 mov r20,r16
 lsr r16
 subi r16,-2
 sbrc r20,0
 neg r16
pitch_add:
 add r14,r16
 rjmp read_gain
pitch_literal:
 ldi r22,8
 rcall read_bits
 mov r14,r16
read_gain:
 mov r16,r4
 swap r16
 andi r16,7
 ldi r22,3
 rcall changed
 mov r20,r16
 swap r20
 mov r16,r4
 andi r16,15
 or r16,r20
 mov r4,r16
 tst r20
 breq read_level
 rcall read_bit
 clr r16
 ror r16
 or r4,r16
 mov r16,r4
 andi r16,15
 ldi r22,4
 rcall changed
 mov r20,r4
 andi r20,0xf0
 or r16,r20
 mov r4,r16
read_level:
 mov r16,r5
 andi r16,15
 ldi r22,4
 rcall changed
 mov r20,r5
 andi r20,0x30
 or r20,r16
 mov r5,r20
 tst r16
 breq frame_done
.if ENABLE_FIR
 mov r16,r5
 swap r16
 andi r16,3
 ldi r22,2
 rcall changed
 swap r16
 mov r20,r5
 andi r20,15
 or r16,r20
 mov r5,r16
.else
 /* All active residuals are white: the encoded repeat-color flag is zero. */
 rcall read_bit
.endif
frame_done:
 sts BITBUF,r17
 ret
changed:
 rcall read_bit
 brcs read_bits
 ret
read_bits:
 clr r16
 ldi r19,1
read_bits_loop:
 rcall read_bit
 brcc read_bits_skip
 or r16,r19
read_bits_skip:
 lsl r19
 dec r22
 brne read_bits_loop
 ret
read_bit:
 lsr r17
 brne bit_done
 movw r30,r26
 lpm r17,Z+
 movw r26,r30
 ror r17
bit_done:
 ret

irq:
 push r16
 in r16,0x3f
 push r16
 dec r9
 brne irq_done
 ldi r16,5
 mov r9,r16
 tst r8
 breq irq_done
 out 0x29,r7
 clr r8
irq_done:
 pop r16
 out 0x3f,r16
 pop r16
 reti
decoder_end:
wave_data:
.incbin "model-avr.bin"
.set noise_data,wave_data+WAVE_BYTES
.set field_data,wave_data+WAVE_BYTES+FIR_BYTES
