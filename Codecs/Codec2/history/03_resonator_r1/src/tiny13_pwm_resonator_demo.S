/* ATtiny13A Codec2 3200 second-order sine resonator demonstration.
 * F_CPU = 9.6MHz, CKDIV8 off (low fuse 0x7A).
 * PB1/OC0B fast PWM at 37500 Hz, signal 8000 samples/sec.
 * ISR does NOT compute samples: resonators run in main loop.
 * One fixed real Codec2 frame is repeated; external streaming not included.
 */
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
    ldi r16,0x9f         /* top SRAM */
    out 0x3d,r16         /* SPL */
    rcall codec2tiny_init
    ldi r30,lo8(demo_packet)
    ldi r31,hi8(demo_packet)
    ldi r26,FRAME
    clr r27
    ldi r18,8
copy_frame:
    lpm r20,Z+
    st X+,r20
    dec r18
    brne copy_frame
    rcall codec2tiny_decode_frame

    ldi r16,0x02        /* PB1 output */
    out 0x17,r16        /* DDRB */
    ldi r16,128
    out 0x29,r16        /* OCR0B */
    ldi r16,0x23        /* COM0B1|WGM01|WGM00 */
    out 0x2f,r16        /* TCCR0A */
    ldi r16,0x01        /* CS00, /1 */
    out 0x33,r16        /* TCCR0B */
    out 0x39,r16        /* TIMSK0 = TOIE0 */
    sei

/* When the ISR consumes NEXTPCM it clears READY; main produces one sample.
 * Main calculation may take >256 CPU clocks but should take <1200.
 */
main_loop:
    lds r16,READY
    tst r16
    brne main_loop
    rcall codec2tiny_sample
    sts NEXTPCM,r16
    ldi r16,1
    sts READY,r16
    rjmp main_loop

pwm_ovf_irq:
    push r16
    in r16,0x3f
    push r16
    push r17
    lds r16,PWM_ACC
    subi r16,0xf0       /* +16 */
    cpi r16,75
    brlo pwm_irq_no_sample
    subi r16,75
    sts PWM_ACC,r16
    lds r17,READY
    tst r17
    breq pwm_irq_exit
    lds r16,NEXTPCM
    out 0x29,r16
    clr r16
    sts READY,r16
    rjmp pwm_irq_exit
pwm_irq_no_sample:
    sts PWM_ACC,r16
pwm_irq_exit:
    pop r17
    pop r16
    out 0x3f,r16
    pop r16
    reti

#include "codec2tiny_resonator.S"

demo_packet:
    .byte 0xcd,0xf1,0x42,0x26,0x81,0x94,0xb7,0x82
