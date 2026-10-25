/* Optional hardware FIFO driver. Same behavior as the C ISR in platform.c. */
#include <avr/io.h>
#include "audio-buffer.h"
#include "audio-channels.h"
#include "irq-scratch.h"
#if defined(__AVR_ATtiny88__) && defined(UM_ENABLE_AVR_ASM) && UM_ENABLE_AVR_ASM
.text
.global TIMER1_OVF_vect
.type TIMER1_OVF_vect,@function
TIMER1_OVF_vect:
#if UM_IRQ_GPIOR_SCRATCH
    /* Explicit hardware resource claim: no other application code may use
       these registers while this non-nested IRQ is enabled. CPU registers,
       including a possibly nonzero r1, are always restored in full. */
    out _SFR_IO_ADDR(GPIOR0),r16
    out _SFR_IO_ADDR(GPIOR1),r26
    out _SFR_IO_ADDR(GPIOR2),r27
#else
    push r16
    push r26
    push r27
#endif
    lds r26,um_read
    lds r16,um_write
    /* CPSE and the complete nonempty path leave every SREG bit unchanged.
       Only the empty-path counter increment needs an SREG snapshot. */
    cpse r26,r16
    rjmp .Lnonempty
    /* X is not needed on the empty path, and r27 is already backed up. */
    in r27,_SFR_IO_ADDR(SREG)
    lds r16,um_underruns
    inc r16
    sts um_underruns,r16
    out _SFR_IO_ADDR(SREG),r27
    rjmp .Lrestore
.Lnonempty:
    /* platform.c guarantees a 256-byte-aligned FIFO, shorter than a page. */
    ldi r27,hi8(um_ring)
    ld r16,X+
#if UM_OUTPUT_CHANNELS == 2
    sts _SFR_MEM_ADDR(OCR1AL),r16
    ld r16,X+
#endif
    sts _SFR_MEM_ADDR(OCR1BL),r16
#if (UM_PWM_BUFFER_FRAMES & (UM_PWM_BUFFER_FRAMES-1)) == 0
    /* A valid cursor advances to the capacity, never beyond it. For a power
       of two, its first out-of-range bit is an exact flag-neutral wrap test. */
#if UM_PWM_BUFFER_FRAMES == 8
    sbrc r26,3
#elif UM_PWM_BUFFER_FRAMES == 16
    sbrc r26,4
#elif UM_PWM_BUFFER_FRAMES == 32
    sbrc r26,5
#elif UM_PWM_BUFFER_FRAMES == 64
    sbrc r26,6
#elif UM_PWM_BUFFER_FRAMES == 128
    sbrc r26,7
#endif
    ldi r26,0
    sts um_read,r26
#else
    ldi r27,UM_PWM_BUFFER_FRAMES
    ldi r16,0
    cpse r26,r27
    mov r16,r26
    sts um_read,r16
#endif
.Lrestore:
#if UM_IRQ_GPIOR_SCRATCH
    in r27,_SFR_IO_ADDR(GPIOR2)
    in r26,_SFR_IO_ADDR(GPIOR1)
    in r16,_SFR_IO_ADDR(GPIOR0)
#else
    pop r27
    pop r26
    pop r16
#endif
    reti
.size TIMER1_OVF_vect,.-TIMER1_OVF_vect
#endif
