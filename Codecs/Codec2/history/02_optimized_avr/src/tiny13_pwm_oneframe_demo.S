/* ATtiny13A independent smoke-test firmware: repeats ONE real Codec2 frame.
 * PWM: PB1/OC0B, fast PWM 9.6MHz/256=37.5kHz carrier.
 * Timer0 overflow ISR fractional divider: 16 ticks every 75 overflows = 8kHz.
 * This is NOT yet a streaming audio player.  The 8-byte test frame resides
 * in Flash to demonstrate boot, decoding, timer, PWM and a continual tone.
 * No hardware MUL, no dependencies on libc, fuses CKDIV8 OFF (lfuse=0x7A).
 */
.equ PWM_ACC, 0x7c
.text
.global reset
rjmp reset               /* 0 RESET */
rjmp unused_vector       /* 1 INT0 */
rjmp unused_vector       /* 2 PCINT0 */
rjmp pwm_ovf_irq         /* 3 TIMER0_OVF */
rjmp unused_vector       /* 4 EEPROM ready */
rjmp unused_vector       /* 5 ANALOG COMP */
rjmp unused_vector       /* 6 TIMER0_COMPA */
rjmp unused_vector       /* 7 TIMER0_COMPB */
rjmp unused_vector       /* 8 WDT */
rjmp unused_vector       /* 9 ADC */
unused_vector:
    reti
reset:
    ldi r16, 0x9f         /* SRAM upper bound */
    out 0x3d, r16         /* SPL */
    clr r16
    sts PWM_ACC,r16
    rcall codec2tiny_init
    /* Copy flash-resident Codec2 frame into SRAM input area at 0x60. */
    ldi r30, lo8(demo_packet)
    ldi r31, hi8(demo_packet)
    ldi r26, 0x60
    clr r27
    ldi r18,8
copy_frame:
    lpm r20,Z+
    st X+,r20
    dec r18
    brne copy_frame
    rcall codec2tiny_decode_frame

    /* PB1 output, Timer0 fast PWM on OC0B, prescaler /1. */
    ldi r16, 0x02
    out 0x17,r16          /* DDRB = PB1 output */
    ldi r16, 128
    out 0x29,r16          /* OCR0B = midpoint */
    ldi r16, 0x23         /* COM0B1 + WGM01 + WGM00 */
    out 0x2f,r16          /* TCCR0A */
    ldi r16,0x01          /* CS00 */
    out 0x33,r16          /* TCCR0B */
    out 0x39,r16          /* TIMSK0: TOIE0 */
    sei
play_forever:
    rjmp play_forever

pwm_ovf_irq:
    push r16
    in r16,0x3f           /* SREG */
    push r16
    push r17
    push r18
    push r19
    push r20
    push r21
    lds r16,PWM_ACC
    subi r16,0xf0         /* +16 mod 256 */
    cpi r16,75
    brlo no_new_sample
    subi r16,75
    sts PWM_ACC,r16
    rcall codec2tiny_sample
    out 0x29,r16          /* set 8-bit PWM amplitude */
    rjmp pwm_irq_exit
no_new_sample:
    sts PWM_ACC,r16
pwm_irq_exit:
    pop r21
    pop r20
    pop r19
    pop r18
    pop r17
    pop r16
    out 0x3f,r16
    pop r16
    reti

#include "codec2tiny3200.S"

/* A voiced frame taken directly from ZX Spectrum Codec2 3200 test stream,
 * voiced0=voiced1=1, pitch_index=18, energy_index=23. */
demo_packet:
    .byte 0xcd,0xf1,0x42,0x26,0x81,0x94,0xb7,0x82
