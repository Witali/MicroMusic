/*
 * Codec2 3200 parameter -> 3 second-order excited sine resonators.
 * ATtiny13A, F_CPU=9600000, CKDIV8 disabled, no hardware MUL.
 * Reads one standard Gray coded 8-byte Codec2 3200 packet in SRAM FRAME.
 * Produces 8000 unsigned samples/s in r16. NOT reference Codec2 synthesis.
 * The oscillator is a semi-implicit, damped two-integrator second order
 * resonator: v <- v - trunc(k*y/128) - sign(v)*ceil(abs(v)/16) + exc;
 *            y <- y + trunc(k*v/128).
 * Its frequency is determined by k ~= 256*sin(pi*f/8000). The resonance is
 * excited by f0 period pulses (voiced) or noise (unvoiced). It is not a
 * square-wave oscillator. k looked up in Flash at 100Hz increments.
 * All multiplies are software 8x8 signed/unsigned shift-and-add.
 * NOTE registers are PRIVATE AVR assembly ABI, not avr-gcc calling convention.
 */
.equ FRAME,    0x60 /* 8 input bytes */
.equ VOICE0,   0x68
.equ VOICE1,   0x69
.equ PITCH,    0x6a
.equ ENERGY,   0x6b
.equ F0LO,     0x6c
.equ F0HI,     0x6d
.equ COEFF,    0x6e /* k0,k1,k2, unsigned Q7 */
.equ FILTER,   0x71 /* v0,y0,v1,y1,v2,y2 : signed 8-bit */
.equ NOISE,    0x77
.equ SAMPLE,   0x78
.equ PHASELO,  0x79
.equ PHASEHI,  0x7a
.equ NEXTPCM,  0x7b
.equ READY,    0x7c
.equ PWM_ACC,  0x7d

.text
.global codec2tiny_init
.global codec2tiny_decode_frame
.global codec2tiny_sample

codec2tiny_init:
    clr r16
    sts FILTER+0,r16
    sts FILTER+1,r16
    sts FILTER+2,r16
    sts FILTER+3,r16
    sts FILTER+4,r16
    sts FILTER+5,r16
    sts SAMPLE,r16
    sts PHASELO,r16
    sts PHASEHI,r16
    sts READY,r16
    sts PWM_ACC,r16
    ldi r16,128
    sts NEXTPCM,r16
    ldi r16,0xa5
    sts NOISE,r16
    ret

/* Parse fixed Codec2 3200 frame, derive pitch step and three formants. */
codec2tiny_decode_frame:
    ldi r26,FRAME
    clr r27
    ldi r16,128
    mov r15,r16          /* Gray bit mask */
    ldi r18,1
    rcall read_gray
    sts VOICE0,r20
    ldi r18,1
    rcall read_gray
    sts VOICE1,r20
    ldi r18,7
    rcall read_gray
    sts PITCH,r20

    /* 16-bit pitch phase increment: round(409.6 + 22.4*p).
     * 22.375*p approx: 16*p + 4*p + 2*p + p/4 + p/8.
     * This is substantially more accurate than snapping f0 to 25 Hz.
     */
    mov r23,r20
    ldi r18,lo8(410)
    ldi r19,hi8(410)
    mov r20,r23
    clr r21
    lsl r20
    rol r21             /* p*2 */
    add r18,r20
    adc r19,r21
    lsl r20
    rol r21             /* p*4 */
    add r18,r20
    adc r19,r21
    lsl r20
    rol r21             /* p*8 */
    lsl r20
    rol r21             /* p*16 */
    add r18,r20
    adc r19,r21
    mov r20,r23
    lsr r20
    lsr r20
    add r18,r20
    ldi r21,0         /* preserve carry from ADD; CLR would destroy it */
    adc r19,r21
    lsr r20             /* p/8 */
    add r18,r20
    adc r19,r21
    sts F0LO,r18
    sts F0HI,r19

    ldi r18,5
    rcall read_gray
    sts ENERGY,r20
    clr r24             /* cumulative LSP delta in 25Hz units */

    ldi r18,5
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
    ror r20             /* average LSP frequency in 25Hz units */
    rcall formant_coeff
    sts COEFF+0,r20

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
    rcall formant_coeff
    sts COEFF+1,r20

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
    rcall formant_coeff
    sts COEFF+2,r20
    clr r16
    sts SAMPLE,r16
    ret

/* X=frame byte pointer; r15=mask; r18=field width, r20=decoded. */
read_gray:
    clr r20
    clr r22
read_gray_bit:
    lsl r20
    ld r21,X
    and r21,r15
    breq read_gray_zero
    ldi r21,1
read_gray_zero:
    eor r22,r21
    or r20,r22
    lsr r15
    brne read_gray_cont
    ldi r16,128
    mov r15,r16
    adiw r26,1
read_gray_cont:
    dec r18
    brne read_gray_bit
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

/* LSP pair centre r20 in 25Hz, k=2sin(pi*f/8000) in Q7.
 * 31-byte table, nearest 100Hz, clamp to 3000Hz to preserve stability.
 * X pointer, r15, r24/r25 survive; Z is scratch.
 */
formant_coeff:
    lsr r20
    lsr r20             /* 100Hz bin */
    cpi r20,31
    brlo coeff_ok
    ldi r20,30
coeff_ok:
    ldi r30,lo8(coeff_table)
    ldi r31,hi8(coeff_table)
    add r30,r20
    clr r21
    adc r31,r21
    lpm r20,Z
    ret

/* Produce one 8kHz PCM sample in r16; preserve none of r16..r31. */
codec2tiny_sample:
    lds r18,SAMPLE
    cpi r18,80
    brlo voiced_first
    lds r17,VOICE1
    rjmp voiced_selected
voiced_first:
    lds r17,VOICE0
voiced_selected:
    inc r18
    cpi r18,160
    brlo sample_counter_valid
    clr r18
sample_counter_valid:
    sts SAMPLE,r18

    /* pitch accumulator, carry is the excitation pulse. */
    lds r18,PHASELO
    lds r19,PHASEHI
    lds r20,F0LO
    add r18,r20
    lds r20,F0HI
    adc r19,r20
    sts PHASELO,r18
    sts PHASEHI,r19
    brcc no_pitch_pulse
    ldi r18,1
    rjmp pulse_saved
no_pitch_pulse:
    clr r18
pulse_saved:
    tst r17
    breq unvoiced_excitation
    clr r17
    tst r18
    breq excitation_ready
    lds r17,ENERGY
    lsr r17
    lsr r17
    /* small pulse, prevent overflow and spectral splatter */
    inc r17
    rjmp excitation_ready
unvoiced_excitation:
    lds r18,NOISE
    mov r20,r18
    lsl r20
    lsl r20
    lsl r20
    eor r18,r20
    mov r20,r18
    lsr r20
    lsr r20
    lsr r20
    lsr r20
    lsr r20
    eor r18,r20
    mov r20,r18
    lsl r20
    eor r18,r20
    sts NOISE,r18
    lds r17,ENERGY
    lsr r17
    lsr r17
    lsr r17
    inc r17
    sbrc r18,7
    neg r17
excitation_ready:
    clr r16            /* signed PCM accumulator */
    ldi r26,COEFF
    clr r27
    ldi r30,FILTER
    clr r31
    ldi r19,3
resonator_loop:
    ld r29,X+          /* unsigned Q7 coefficient */
    ld r28,Z+          /* v[n-1]; Z points to y */
    ld r20,Z           /* y[n-1] */
    mov r21,r29
    rcall mul_coeff     /* r22 = signed trunc(k*y/128) */
    sub r28,r22        /* v -= k*y/128 */
    mov r20,r28
    sbrc r20,7
    rjmp damp_round_ok
    /* protect values +113..+127 from wrap when adding the rounding bias */
    cpi r20,113
    brlo damp_add_bias
    ldi r20,8
    rjmp damp_apply
damp_add_bias:
    subi r20,0xf1      /* add 15 for positive v: nonzero damping */
damp_round_ok:
    asr r20
    asr r20
    asr r20
    asr r20            /* damping approx ceil(|v|/16) */
damp_apply:
    sub r28,r20
    add r28,r17        /* common voiced pulse/noise excitation */
    st -Z,r28          /* Z returns to v */
    mov r20,r28
    mov r21,r29
    rcall mul_coeff
    adiw r30,1         /* Z moves to y */
    ld r20,Z
    add r20,r22        /* y += k*v/128 */
    st Z+,r20
    add r16,r20        /* sum 3 resonator outputs */
    dec r19
    brne resonator_loop
    /* Saturate summed formants to [-64,+63] BEFORE 2x gain. */
    sbrc r16,7
    rjmp sample_negative
    cpi r16,64
    brlo sample_gain
    ldi r16,63
    rjmp sample_gain
sample_negative:
    cpi r16,192
    brcc sample_gain
    ldi r16,192
sample_gain:
    lsl r16            /* 2x output gain, signed 8bit -> unsigned PWM */
    subi r16,128       /* add midpoint 128 modulo 256 */
    ret

/* Signed 8bit x in r20 * unsigned 8bit coefficient r21,
 * -> signed trunc((x*coeff)/128) low byte in r22, high byte r23.
 * 8 partial products in 16-bit arithmetic; absolutely no MUL instruction.
 * Clobbers r18,r21..r25; leaves X,Z,r16,r17,r19,r28,r29 intact.
 */
mul_coeff:
    mov r24,r20
    clr r25
    sbrc r24,7
    dec r25
    clr r22
    clr r23
    ldi r18,8
mul_bit:
    sbrs r21,0
    rjmp mul_skip
    add r22,r24
    adc r23,r25
mul_skip:
    lsl r24
    rol r25
    lsr r21
    dec r18
    brne mul_bit
    /* For negative products add 127 before >>7: symmetric truncation. */
    sbrs r23,7
    rjmp mul_round_done
    ldi r24,127
    add r22,r24
    ldi r24,0          /* preserve carry from ADD */
    adc r23,r24
mul_round_done:
    ldi r18,7
mul_shift:
    asr r23
    ror r22
    dec r18
    brne mul_shift
    ret

/* k = round(256*sin(pi*f/8000)) at f=0,100,..3000Hz. */
coeff_table:
    .byte 0,10,20,30,40,50,60,69,79,89,98,107,116,125,134,142
    .byte 150,158,166,174,181,188,195,201,207,213,218,223,228,232,237
