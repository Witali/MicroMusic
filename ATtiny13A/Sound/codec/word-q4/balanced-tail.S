/* Q1 zero-area tail: signed area r18 (-112..112), tail index r19 (0..15).
 * Result r24 is a signed Q1 tap (-7..7). Clobbers r20 and arithmetic flags.
 * Preserves all other registers and SREG.T/I; no SRAM or EEPROM access.
 * Every input takes 17 cycles through RET, excluding the caller's RCALL.
 * The caller still supplies the area descriptor, head reads and pitch state.
 */
.global balanced_tail_q1, balanced_tail_end, balanced_tail_compare
balanced_tail_q1:
 mov r24,r18
 sbrc r24,7
 neg r24
 mov r20,r24
 andi r20,15
 swap r24
 andi r24,15
 add r20,r19
 cpi r20,16
balanced_tail_compare:
 brlo balanced_tail_sign
 inc r24
balanced_tail_sign:
 sbrc r18,7
 neg r24
 ret
balanced_tail_end:
