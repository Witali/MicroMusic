/* Optional hardware FIFO driver. Same behavior as the C ISR in platform.c. */
#include <avr/io.h>
#include "audio-buffer.h"
#if defined(__AVR_ATtiny88__) && defined(UM_ENABLE_AVR_ASM) && UM_ENABLE_AVR_ASM
.text
.global TIMER1_OVF_vect
.type TIMER1_OVF_vect,@function
TIMER1_OVF_vect:
    push r16
    in r16,_SFR_IO_ADDR(SREG)
    push r16
    push r26
    push r27
    lds r26,um_read
    lds r16,um_write
    cp r26,r16
    breq 1f
    ldi r27,0
    subi r26,lo8(-(um_ring))
    sbci r27,hi8(-(um_ring))
    lds r16,um_channels
    cpi r16,2
    ld r16,X+
    brne .Lmono_frame
    sts _SFR_MEM_ADDR(OCR1AL),r16
    ld r16,X+
.Lmono_frame:
    sts _SFR_MEM_ADDR(OCR1BL),r16
    subi r26,lo8(um_ring)
    cpi r26,UM_PWM_BUFFER_FRAMES
    brcs 3f
    ldi r26,0
3:
    sts um_read,r26
2:
    pop r27
    pop r26
    pop r16
    out _SFR_IO_ADDR(SREG),r16
    pop r16
    reti
1:
    lds r16,um_underruns
    inc r16
    sts um_underruns,r16
    rjmp 2b
.size TIMER1_OVF_vect,.-TIMER1_OVF_vect
#endif
