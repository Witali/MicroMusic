/* Exact NB1 mean, classic AVR5 / GNU ABI. C fallback in lowrate_mean.h.
 * old r24:25, value r22:23 -> signed16 result r24:25. Caller-clobbered
 * registers/flags only; r1 cleared, no stack or interrupt masking. */
#include "lowrate_mean_kernel.inc"
.text
.global speex_low_mean_avr
.type speex_low_mean_avr,@function
speex_low_mean_avr:
    SPEEX_NB1_MEAN r24,r25,r26,r27
    ret
.size speex_low_mean_avr,.-speex_low_mean_avr
