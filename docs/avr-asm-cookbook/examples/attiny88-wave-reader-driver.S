#include <avr/io.h>
.section .vectors,"ax",@progbits
.global vectors
vectors:
  rjmp reset
reset:
  cli
  clr r1
  ldi r16, hi8(RAMEND)
  out _SFR_IO_ADDR(SPH), r16
  ldi r16, lo8(RAMEND)
  out _SFR_IO_ADDR(SPL), r16
  ldi r28, lo8(observed)
  ldi r29, hi8(observed)
  clr r16
next_sample:
  /* R16 and Y are callee-saved in the GNU AVR C ABI. */
  mov r24, r16
  rcall read_sample
  st Y+, r24
  inc r16
  cpi r16, 64
  brne next_sample
  ldi r17, 0xa5
  sts complete, r17
finished:
  rjmp finished
