/* MicroMusic / ATtiny13A / experimental TinyLPC speech player
 * 9.6 MHz internal RC, Timer0 Fast PWM @ 37500 Hz on OC0B/PB1.
 * The ISR writes the next buffered 8-bit sample every fifth overflow:
 *   37500/5 = 7500 Hz PCM, derived from a bandwidth-limited 8-stage lattice vocoder.
 * Main code synthesizes frames into a 16-byte ring in SRAM.
 * Adaptive keyframe stream: fast/slow transition bit in pitch header,
 * spectral keyframes, short events, and RLE silence; Flash-resident data.
 * All RAM accesses are >= 0x60. Main uses r2-r31; ISR saves own regs.
 */
.section .text
.global __vectors
.set IO_DDRB,   0x17
.set IO_SPL,    0x3d
.set IO_SREG,   0x3f
.set IO_CLKPR,  0x26
.set IO_TCCR0A, 0x2f
.set IO_TCCR0B, 0x33
.set IO_OCR0B,  0x29
.set IO_TIMSK0, 0x39
.set PWM_CTR,   0x60
.set RDPTR,     0x61
.set COEFF_K6,  0x63
.set COEFF_K7,  0x79
.set STATE7,    0x7a
.set RLE_LEFT,  0x75
.set EXMODE,    0x76
.set GAIN_TARGET,0x77
.set PITCH_TARGET,0x78
.set WRPTR,     0x62
.set RING_BEGIN,0x64
.set RING_END,  0x74
.set VOICE_ADDR,0x034a
.set K_ACTIVE, 0x80
.set K_TARGET, 0x88
.org 0x0000
__vectors:
 rjmp reset
.org 0x0006
 rjmp timer0_irq
.org 0x0014
reset:
 cli
 ldi r16, 0x9f
 out IO_SPL, r16
 /* Remove the clock prescaler, regardless of factory CKDIV8. */
 ldi r16, 0x80
 out IO_CLKPR, r16
 clr r16
 out IO_CLKPR, r16
 ldi r16, 5
 sts PWM_CTR, r16
 ldi r16, RING_BEGIN
 sts RDPTR, r16
 sts WRPTR, r16
 mov r19, r16
 /* State b0...b6; the 7th reflection coefficient lives in SRAM. */
 clr r14
 clr r15
 clr r11
 clr r17
 clr r18
 clr r12
 clr r13
 sts STATE7,r13
 clr r0
 clr r1
 clr r10                  /* Frame sample count modulo 256. */
 ldi r28,K_ACTIVE
 clr r29
 ldi r25,16
clr_coeffs:
 st Y+,r10
 dec r25
 brne clr_coeffs
 clr r5
 clr r4
 sts RLE_LEFT,r5
 ldi r16, 1
 mov r2,r16              /* Pitch pulse countdown. */
 ldi r16,0xa7
 mov r3,r16              /* 8-bit LFSR noise. */
 ldi r30,lo8(VOICE_ADDR)
 ldi r31,hi8(VOICE_ADDR)
 rcall read_frame
 sbi IO_DDRB,1
 ldi r16,128
 out IO_OCR0B,r16
 ldi r16,0x23             /* COM0B1 + WGM01 + WGM00. */
 out IO_TCCR0A,r16
 ldi r16,1                /* Timer0 no prescaling. */
 out IO_TCCR0B,r16
 ldi r16,2                /* TOIE0. */
 out IO_TIMSK0,r16
 sei

main:
 /* No waiting/synthesis inside interrupt. Only fill when ring has space. */
 mov r20,r19
 inc r20
 cpi r20,RING_END
 brne next_slot_ok
 ldi r20,RING_BEGIN
next_slot_ok:
 lds r16,RDPTR
 cp r20,r16
 breq main
 inc r10
 brne active_frame
 rcall read_frame
active_frame:
 /* Per-frame adaptive quantized-domain slew: all eight lattice reflection
  * coefficients and amplitude approach new keyframe targets by 1 step
  * every 4 samples (0.53 ms). No full-frame discontinuities.
  */
 mov r16,r10
 and r16,r6
 brne skip_smoothing
 rcall smooth_coeffs
 lds r16,GAIN_TARGET
 cp r5,r16
 breq skip_smoothing
 brlt gain_up
 dec r5
 rjmp skip_smoothing
gain_up:
 inc r5
skip_smoothing:
 /* Small interpolated F0 glides between voiced frames. */
 mov r16,r10
 andi r16,7
 brne pitch_ready
 lds r16,PITCH_TARGET
 cp r4,r16
 breq pitch_ready
 brlo pitch_rise
 dec r4
 rjmp pitch_ready
pitch_rise:
 inc r4
pitch_ready:
 /* Default gain is already loaded by read_frame. */
 /* Excitation: four-tap glottal chirp [2,3,2,-1] for voiced frames.
  * The pitch phase is measured by comparing r4 (period) with r2 (countdown).
  * For unvoiced consonants, drive the filter using LFSR noise.
  */
 tst r4
 breq noise_sample
 dec r2
 breq pitch_pulse_start
 mov r22,r4
 sub r22,r2                  /* number of samples after the pulse */
 cpi r22,1
 breq pitch_pulse_second
 cpi r22,2
 breq pitch_pulse_third
 cpi r22,3
 breq pitch_pulse_fourth
 clr r22
 rjmp do_lattice
pitch_pulse_start:
 mov r2,r4
pitch_pulse_third:
 mov r22,r5
 lsl r22                      /* 2*gain */
 rjmp do_lattice
pitch_pulse_second:
 mov r22,r5
 lsl r22                      /* 2*gain */
 add r22,r5                   /* 3*gain */
 rjmp do_lattice
pitch_pulse_fourth:
 mov r22,r5
 neg r22                      /* -1*gain */
 rjmp do_lattice
noise_sample:
 lsr r3
 brcc noise_ready
 ldi r16,0xb8
 eor r3,r16
noise_ready:
 mov r22,r5
 sbrc r3,0
 neg r22

/* Eight-stage all-pole synthesis lattice.
 * For m=7..1: y -= k[m] * b[m-1]; b[m] = b[m-1] + k[m] * y
 * Last: b[0] = y.
 * MAC is signed (8 x 4 bit) with an arithmetic /16 fixed-point shift.
 * The second multiplication uses the UPDATED forward excitation.
 */
do_lattice:
pure_lattice:
 /* m=8, state7. State8 is never used, so skip its update. */
 lds r21,STATE7
 lds r23,K_ACTIVE+7
 rcall mul_q3
 sub r22,r24

 /* m=7, state6 -> state7. */
 mov r21,r13
 lds r23,K_ACTIVE+6
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 lds r23,K_ACTIVE+6
 rcall mul_q3
 mov r16,r13
 add r16,r24
 sts STATE7,r16

 /* m=6, state5 -> state6. */
 mov r21,r12
 lds r23,K_ACTIVE+5
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 lds r23,K_ACTIVE+5
 rcall mul_q3
 mov r13,r12
 add r13,r24

 /* m=5, state4 -> state5. */
 mov r21,r18
 lds r23,K_ACTIVE+4
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 lds r23,K_ACTIVE+4
 rcall mul_q3
 mov r12,r18
 add r12,r24

 mov r21,r17
 lds r23,K_ACTIVE+3
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 lds r23,K_ACTIVE+3
 rcall mul_q3
 mov r18,r17
 add r18,r24

 mov r21,r11
 lds r23,K_ACTIVE+2
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 lds r23,K_ACTIVE+2
 rcall mul_q3
 mov r17,r11
 add r17,r24

 mov r21,r15
 lds r23,K_ACTIVE+1
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 lds r23,K_ACTIVE+1
 rcall mul_q3
 mov r11,r15
 add r11,r24

 mov r21,r14
 lds r23,K_ACTIVE+0
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 lds r23,K_ACTIVE+0
 rcall mul_q3
 mov r15,r14
 add r15,r24
 mov r14,r22

 /* Write one 8-bit signed sample +128 into the 16-byte SRAM ring. */
 mov r16,r22
 subi r16, 128
 mov r28,r19
 clr r29
 st Y,r16
 mov r19,r20
 sts WRPTR,r19
 rjmp main

/* Signed (r21 * r23) >> 4. Coefficients are signed -7..7.
 * AVR ATtiny13A has NO hardware MUL; max 7 additions per call.
 * On entry: r21 = sample, r23 = coefficient. Exit: r24 = scaled product.
 * Clobbers: r21,r23,r24,r25,r26,r27,flags. Does not alter r22.
 */
mul_q3:
 clr r24
 clr r25
 mov r27,r23
 tst r27
 breq mult_done
 brpl positive_k
 neg r27
 neg r21
positive_k:
 mov r26,r21
 clr r23
 sbrc r21,7
 ser r23
mult_loop:
 add r24,r26
 adc r25,r23
 dec r27
 brne mult_loop
mult_done:
 asr r25
 ror r24
 asr r25
 ror r24
 asr r25
 ror r24
 asr r25
 ror r24
 ret

/* Five bytes per frame:
 *  0: pitch period in 7500Hz samples, 0 => unvoiced
 *  1: K0 index in high nibble, energy in low nibble
 *  2: K2 index in high nibble, K1 in low nibble
 *  3: K4 high nibble, K3 low nibble.
 *  4: K6 high nibble, K5 low nibble. Each signed index is the quantized lattice value k*16 + 8,
 * with extra damping for robust 8-bit filter states.
 * The optional 0xff pitch byte loops back to the first frame.
 */
smooth_coeffs:
 /* Active coefficients at 0x80..0x87, targets at 0x88..0x8f.
  * SRAM 0x90..0x9f stays free for the hardware stack.
  * Difference of +/-1 per 4 samples => <=14 steps to a new formant.
  */
 ldi r28,K_ACTIVE
 clr r29
 ldi r26,K_TARGET
 clr r27
 ldi r25,8
smooth_loop:
 ld r16,Y
 ld r23,X
 cp r16,r23
 breq smooth_next
 brlt smooth_up
 dec r16
 rjmp smooth_store
smooth_up:
 inc r16
smooth_store:
 st Y,r16
smooth_next:
 inc r28
 inc r26
 dec r25
 brne smooth_loop
 ret

read_frame:
 mov r23,r4  /* previous pitch for short F0 glide */
 /* A silence run stays silent; first command already reset filter states. */
 lds r16,RLE_LEFT
 tst r16
 breq fetch_frame
 dec r16
 sts RLE_LEFT,r16
 ret
fetch_frame:
 lpm r4,Z+
 mov r16,r4
 cpi r16,0xff
 brne check_silence
 ldi r30,lo8(VOICE_ADDR)
 ldi r31,hi8(VOICE_ADDR)
 lpm r4,Z+
check_silence:
 mov r16,r4
 cpi r16,0xe0
 brlo normal_frame
 subi r16,0xe1
 sts RLE_LEFT,r16
 rjmp silent_frame
normal_frame:
 /* Bits 0..5: pitch, bit7: only gain/F0 update (keep spectrum).
  * In a full frame 4 packed bytes update the eight lattice targets.
  */
 mov r27,r4
 /* Pitch header bit6: slow 8-sample spectral/gain slew by default,
  * fast 4-sample slew for significant phonetic transitions.
  * Bit7 continues to mean short event (no spectral coefficient update).
  * r6 is free from all 8-stage lattice and interrupt routines.
  */
 ldi r16,7
 sbrc r27,6
 ldi r16,3
 mov r6,r16
 mov r16,r4
 andi r16,0x3f
 mov r4,r16
 sts PITCH_TARGET,r4
 mov r16,r4
 sub r16,r23
 subi r16,252
 cpi r16,9
 brsh have_pitch
 mov r4,r23
have_pitch:
 lpm r16,Z+
 mov r24,r16
 andi r16,15
 sts GAIN_TARGET,r16
 tst r16
 breq clear_lattice_states
 sbrc r27,7
 ret
 mov r16,r24
 swap r16
 andi r16,15
 subi r16,8
 sts K_TARGET+0,r16
 lpm r16,Z+
 mov r24,r16
 andi r16,15
 subi r16,8
 sts K_TARGET+1,r16
 mov r16,r24
 swap r16
 andi r16,15
 subi r16,8
 sts K_TARGET+2,r16
 lpm r16,Z+
 mov r24,r16
 andi r16,15
 subi r16,8
 sts K_TARGET+3,r16
 mov r16,r24
 swap r16
 andi r16,15
 subi r16,8
 sts K_TARGET+4,r16
 lpm r16,Z+
 mov r24,r16
 andi r16,15
 subi r16,8
 sts K_TARGET+5,r16
 mov r16,r24
 swap r16
 andi r16,15
 subi r16,8
 sts K_TARGET+6,r16
 lpm r16,Z+
 andi r16,15
 subi r16,8
 sts K_TARGET+7,r16
 ret
silent_frame:
 clr r4
 sts PITCH_TARGET,r4
 clr r5
 sts GAIN_TARGET,r5
clear_lattice_states:
 clr r14
 clr r15
 clr r11
 clr r17
 clr r18
 clr r12
 clr r13
 sts STATE7,r13
 ret

/* ISR runs 37500 times per second, but outputs 7500 PCM samples/s. */
timer0_irq:
 push r16
 in r16,IO_SREG
 push r16
 push r17
 push r18
 push r28
 push r29
 lds r16,PWM_CTR
 dec r16
 brne irq_end
 ldi r16,5
 lds r17,RDPTR
 lds r18,WRPTR
 cp r17,r18
 breq irq_end
 mov r28,r17
 clr r29
 ld r18,Y
 out IO_OCR0B,r18
 inc r17
 cpi r17,RING_END
 brne irq_ptr_ok
 ldi r17,RING_BEGIN
irq_ptr_ok:
 sts RDPTR,r17
irq_end:
 sts PWM_CTR,r16
 pop r29
 pop r28
 pop r18
 pop r17
 pop r16
 out IO_SREG,r16
 pop r16
 reti

.org VOICE_ADDR
voice_data:
.incbin "voice_tinylpc.bin"
.byte 0xff
