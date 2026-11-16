/* X walks the coefficients and Z walks the history, both in reverse.
   The v9 history has a spare word for the first shift.
   Return the coefficient in r19:r18 and the old sample in r21:r20. */
.macro LPX_LOAD_LPC_TAP
	ld r19,-X
	ld r18,-X
	ld r21,-Z
	ld r20,-Z
	std Z+2,r20
	std Z+3,r21
.endm
