/* MicroMusic / ATtiny13A / experimental TinyLPC speech player
 * 9.6 MHz internal RC, Timer0 Fast PWM @ 37500 Hz on OC0B/PB1.
 * The ISR writes the next buffered 8-bit sample every fifth overflow:
 *   37500/5 = 7500 Hz PCM, derived from a 6-stage lattice vocoder.
 * Main code synthesizes frames into a 16-byte ring in SRAM.
 * 5 bytes per 256-sample speech frame; all voice data in Flash.
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
.set WRPTR,     0x62
.set RING_BEGIN,0x64
.set RING_END,  0x74
.set VOICE_ADDR,0x01f0
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
 /* State b0,b1,b2,b3,b4. 6 signed 8-bit reflection coefficients. */
 clr r14
 clr r15
 clr r11
 clr r17
 clr r18
 clr r12
 clr r13
 clr r0
 clr r1
 clr r10                  /* Frame sample count modulo 256. */
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
 /* Generate pitched impulse excitation, or balanced pseudo-random noise. */
 tst r4
 breq noise_sample
 dec r2
 brne quiet_sample
 mov r2,r4
 mov r22,r5
 lsl r22
 rjmp do_lattice
quiet_sample:
 clr r22
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

/* Six-stage all-pole synthesis lattice.
 * For m=6..1: y -= k[m] * b[m-1]; b[m] = b[m-1] + k[m] * y
 * Last: b[0] = y.
 * MAC is signed (8 x 4 bit) with an arithmetic /8 fixed-point shift.
 * The second multiplication uses the UPDATED forward excitation.
 */
do_lattice:
 /* m=6, state5 -> state6. */
 mov r21,r12
 mov r23,r1
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 mov r23,r1
 rcall mul_q3
 mov r13,r12
 add r13,r24

 /* m=5, state4 -> state5. */
 mov r21,r18
 mov r23,r0
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 mov r23,r0
 rcall mul_q3
 mov r12,r18
 add r12,r24

 mov r21,r17
 mov r23,r9
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 mov r23,r9
 rcall mul_q3
 mov r18,r17
 add r18,r24

 mov r21,r11
 mov r23,r8
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 mov r23,r8
 rcall mul_q3
 mov r17,r11
 add r17,r24

 mov r21,r15
 mov r23,r7
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 mov r23,r7
 rcall mul_q3
 mov r11,r15
 add r11,r24

 mov r21,r14
 mov r23,r6
 rcall mul_q3
 sub r22,r24
 mov r21,r22
 mov r23,r6
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

/* Signed (r21 * r23) >> 3. Coefficients are signed -7..7.
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
 ret

/* Five bytes per frame:
 *  0: pitch period in 7500Hz samples, 0 => unvoiced
 *  1: K0 index in high nibble, energy in low nibble
 *  2: K2 index in high nibble, K1 in low nibble
 *  3: K4 high nibble, K3 low nibble.
 *  4: K5 low nibble. Each K index is integer(k*8)+8.
 * The optional 0xff pitch byte loops back to the first frame.
 */
read_frame:
 lpm r4,Z+
 mov r16,r4
 cpi r16,0xff
 brne frame_body
 ldi r30,lo8(VOICE_ADDR)
 ldi r31,hi8(VOICE_ADDR)
 lpm r4,Z+
frame_body:
 lpm r16,Z+
 mov r24,r16
 andi r16,15
 mov r5,r16
 mov r16,r24
 swap r16
 andi r16,15
 subi r16,8
 mov r6,r16
 lpm r16,Z+
 mov r24,r16
 andi r16,15
 subi r16,8
 mov r7,r16
 mov r16,r24
 swap r16
 andi r16,15
 subi r16,8
 mov r8,r16
 lpm r16,Z+
 mov r24,r16
 andi r16,15
 subi r16,8
 mov r9,r16
 mov r16,r24
 swap r16
 andi r16,15
 subi r16,8
 mov r0,r16
 lpm r16,Z+
 andi r16,15
 subi r16,8
 mov r1,r16
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
