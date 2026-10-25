/*
 * codec2tiny3200.S -- very small 8-bit AVR Codec2-3200 bitstream parameter
 * reader and approximate 3-tone/noise waveform synthesizer.
 * Target: ATtiny13A F_CPU=9.6 MHz, CKDIV8=off, no hardware MUL.
 * Inputs: external producer writes one complete 8-byte frame at SRAM 0x60.
 * Usage: codec2tiny_init once, codec2tiny_decode_frame every 20 ms,
 *        codec2tiny_sample every 125 us (8 kHz), sample returned in r16.
 * Calling convention: PRIVATE ASSEMBLY API (r15..r27 clobbered by
 * decode_frame; r16..r21 clobbered by sample), not avr-gcc ABI.
 * Firmware integration, clocked input and PWM ISR are NOT part of this module.
 *
 * Codec2 fields: v0(1), v1(1), pitch(7), energy(5), 10*LSPD(5),
 * all Gray encoded MSB first.  Only first six LSPD values affect synthesis.
 * It accepts standard Codec2 mode-3200 bitstreams but is NOT an acoustically
 * equivalent Codec2 reference decoder.  Avoids LSP->LPC and FFT.
 * Adapted from the author's prior codec2zx Z80/Pentagon prototype.
 * Codec2 reference bitstream format from David Rowe's codec2 (LGPL-2.1).
 */

/* ATtiny13 SRAM starts at 0x60, ends at 0x9f. */
.equ FRAME,  0x60  /* 8-byte frame supplied by external reader */
.equ VOICE0, 0x68
.equ VOICE1, 0x69
.equ PITCH,  0x6a
.equ ENERGY, 0x6b
.equ F0UNIT, 0x6c
.equ LSPPOS, 0x6d
.equ STEPS,  0x6e  /* 3 x uint16 (low,high) */
.equ PHASES, 0x74  /* 3 x uint16 (low,high) */
.equ NOISE,  0x7a
.equ SAMPLE, 0x7b  /* 0..159 within a frame */

.text
.global codec2tiny_init
.global codec2tiny_decode_frame
.global codec2tiny_sample

codec2tiny_init:
    clr r16
    sts PHASES+0, r16
    sts PHASES+1, r16
    sts PHASES+2, r16
    sts PHASES+3, r16
    sts PHASES+4, r16
    sts PHASES+5, r16
    sts SAMPLE, r16
    ldi r16, 0xa5
    sts NOISE, r16
    ret

/* Parse one frame at FRAME address.  r15...r27 clobbered. */
codec2tiny_decode_frame:
    ldi r26, FRAME
    clr r27
    ldi r16, 0x80           /* MSB mask */
    mov r15,r16
    ldi r18, 1
    rcall read_gray
    sts VOICE0, r20
    ldi r18, 1
    rcall read_gray
    sts VOICE1, r20
    ldi r18, 7
    rcall read_gray
    sts PITCH, r20

    /* f0_Hz = 50 + (350*pitch)/128.
     * units of 25 Hz = 2 + pitch*(7/64) rounded by shifts.
     */
    mov r23, r20
    lsr r23
    lsr r23
    lsr r23              /* pitch/8 */
    mov r21, r20
    lsr r21
    lsr r21
    lsr r21
    lsr r21
    lsr r21
    lsr r21              /* pitch/64 */
    sub r23, r21
    subi r23, -2
    sts F0UNIT, r23

    ldi r18, 5
    rcall read_gray
    sts ENERGY, r20

    clr r24               /* running LSP centre position in 25 Hz units */

    /* Pair 0, two simple LSPD scalar quantisers. */
    ldi r18, 5
    rcall read_gray
    inc r20
    add r24,r20
    mov r25,r24
    ldi r18,5
    rcall read_gray
    inc r20
    add r24,r20
    mov r20,r24
    add r20,r25
    ror r20               /* 9-bit sum -> mean */
    rcall snap_and_convert
    sts STEPS+0,r18
    sts STEPS+1,r19

    /* Pair 1: simple + wide LSPD. */
    ldi r18,5
    rcall read_gray
    inc r20
    add r24,r20
    mov r25,r24
    ldi r18,5
    rcall read_gray
    rcall wide_delta
    add r24,r20
    mov r20,r24
    add r20,r25
    ror r20
    rcall snap_and_convert
    sts STEPS+2,r18
    sts STEPS+3,r19

    /* Pair 2: wide + wide LSPD. */
    ldi r18,5
    rcall read_gray
    rcall wide_delta
    add r24,r20
    mov r25,r24
    ldi r18,5
    rcall read_gray
    rcall wide_delta
    add r24,r20
    mov r20,r24
    add r20,r25
    ror r20
    rcall snap_and_convert
    sts STEPS+4,r18
    sts STEPS+5,r19

    clr r16
    sts SAMPLE,r16
    ret

/* Bitstream reader: uses X (r26:r27), r15 = mask, r18=width.
 * Output r20 = decoded binary value; clobbers r21,r22.
 * Traverses Gray input MSB first and tracks parity of previous binary bit.
 */
read_gray:
    clr r20
    clr r22
read_gray_loop:
    lsl r20
    ld r21,X
    and r21,r15
    breq read_gray_zero
    ldi r21,1
read_gray_zero:
    eor r22,r21
    or r20,r22
    lsr r15
    brne read_gray_next
    ldi r16,0x80
    mov r15,r16
    adiw r26,1
read_gray_next:
    dec r18
    brne read_gray_loop
    ret

wide_delta:
    cpi r20,8
    brlo wide_small
    lsl r20
    subi r20,6
    ret
wide_small:
    inc r20
    ret

/* r20=centre frequency in units of 25Hz, r23=f0 in 25Hz units.
 * Snap to harmonic (integer only); map u * 25Hz to DDS frequency step:
 * step = u*205 ~ u*25*65536/8000.  0.10% high.  Output r18:r19.
 * r17/r20/r21/r22 may be clobbered.  Preserve r23:r24:r25 and X and reader mask.
 */
snap_and_convert:
    clr r18
snap_again:
    mov r21,r18
    add r21,r23
    brcs snap_done
    cp r20,r21
    brlo snap_done
    mov r18,r21
    rjmp snap_again
snap_done:
    mov r22,r20
    sub r22,r18
    lsl r22
    cp r22,r23
    brlo snap_floor
    mov r18,r21
snap_floor:
    tst r18
    brne snap_nonzero
    mov r18,r23
snap_nonzero:
    /* multiply by 205 = 128 + 64 + 8 + 4 + 1 */
    mov r20,r18
    clr r19                /* result r19:r18; r20 = original u */
    mov r21,r20
    clr r22
    lsl r21
    rol r22
    lsl r21
    rol r22                /* tmp = u*4 */
    add r18,r21
    adc r19,r22
    lsl r21
    rol r22                /* tmp = u*8 */
    add r18,r21
    adc r19,r22
    lsl r21
    rol r22                /* 16 */
    lsl r21
    rol r22                /* 32 */
    lsl r21
    rol r22                /* 64 */
    add r18,r21
    adc r19,r22
    lsl r21
    rol r22                /* 128 */
    add r18,r21
    adc r19,r22
    ret

/* Return unsigned 8-bit PCM in r16 (127/128 = silence).
 * No hardware multiplication used.  Update three 16-bit DDS phases.
 */
codec2tiny_sample:
    lds r17,SAMPLE
    cpi r17,80
    brlo use_voice0
    lds r18,VOICE1
    rjmp voice_selected
use_voice0:
    lds r18,VOICE0
voice_selected:
    inc r17
    cpi r17,160
    brlo sample_store
    clr r17
sample_store:
    sts SAMPLE,r17
    lds r19,ENERGY
    lsr r19
    ldi r16,128
    tst r18
    breq unvoiced_noise

    lds r20,PHASES+0
    lds r21,STEPS+0
    add r20,r21
    sts PHASES+0,r20
    lds r20,PHASES+1
    lds r21,STEPS+1
    adc r20,r21
    sts PHASES+1,r20
    mov r21,r19
    lsl r21
    lsl r21
    sbrc r20,7
    add r16,r21
    sbrs r20,7
    sub r16,r21

    lds r20,PHASES+2
    lds r21,STEPS+2
    add r20,r21
    sts PHASES+2,r20
    lds r20,PHASES+3
    lds r21,STEPS+3
    adc r20,r21
    sts PHASES+3,r20
    mov r21,r19
    lsl r21
    sbrc r20,7
    add r16,r21
    sbrs r20,7
    sub r16,r21

    lds r20,PHASES+4
    lds r21,STEPS+4
    add r20,r21
    sts PHASES+4,r20
    lds r20,PHASES+5
    lds r21,STEPS+5
    adc r20,r21
    sts PHASES+5,r20
    sbrc r20,7
    add r16,r19
    sbrs r20,7
    sub r16,r19
    ret

unvoiced_noise:
    lds r20,NOISE
    mov r21,r20
    lsl r21
    lsl r21
    lsl r21
    eor r20,r21
    mov r21,r20
    lsr r21
    lsr r21
    lsr r21
    lsr r21
    lsr r21
    eor r20,r21
    mov r21,r20
    lsl r21
    eor r20,r21
    sts NOISE,r20
    mov r21,r19
    lsl r21
    lsl r21
    sbrc r20,7
    add r16,r21
    sbrs r20,7
    sub r16,r21
    ret
