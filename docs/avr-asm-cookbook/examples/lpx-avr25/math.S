#include <avr/io.h>
#include "avr25_math.h"
#if LPX25_USE_ASM
.text
// Original unsigned bit-serial product, then independent signed corrections.
// GNU AVR ABI: x=r25:r24, y=r23:r22, return=r25:r22.
// Only caller-saved r18-r25 are touched. r1 stays zero throughout.
.global proto_mul
.type proto_mul,@function
proto_mul:
    movw r18,r24
    movw r20,r22
    clr r24
    clr r25
    lsr r23
    ror r22
    .rept 16
    brcc 1f
    add r24,r18
    adc r25,r19
1:  ror r25
    ror r24
    ror r23
    ror r22
    .endr
    // Signed x = unsigned x - 65536 iff x<0; likewise for y.
    // The +65536^2 term vanishes modulo2^32.
    sbrs r19,7
    rjmp 2f
    sub r24,r20
    sbc r25,r21
2:  sbrs r21,7
    rjmp 3f
    sub r24,r18
    sbc r25,r19
3:  ret
.size proto_mul,.-proto_mul

// Existing LPX byte-aligned shift identity, adapted only to function ABI.
// Discard low byte, shift the remaining signed24, restore full sign byte.
.macro exact_shift name,remainder
.global \name
.type \name,@function
\name:
    mov r22,r23
    mov r23,r24
    mov r24,r25
    .rept \remainder
    asr r24
    ror r23
    ror r22
    .endr
    lsl r25
    sbc r25,r25
    ret
.size \name,.-\name
.endm
exact_shift proto_shift12,4
exact_shift proto_shift14,6
#endif
