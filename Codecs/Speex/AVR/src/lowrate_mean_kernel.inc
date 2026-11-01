/* Original exact single-product mean, shared by scalar and vector entry.
 * value=r22:r23; oldlo:oldhi updated in place. prodlo is an even register
 * pair, disjoint from old and r18..r23. Clobbers r18,r19,r21,r22,r23,
 * prodlo:prodhi,r0,r1,flags; r20 is preserved for a vector loop counter.
 * Discard product bits0..7: all cross terms and rounding begin at bit8.
 * Overflow correction remains +/-13108. See lowrate_mean.h for C fallback. */
.macro SPEEX_NB1_MEAN oldlo,oldhi,prodlo,prodhi
    sub r22,\oldlo
    sbc r23,\oldhi
    ldi r18,0
    ldi r19,0
    brvc .Lmean_base\@
    ldi r18,lo8(13108)
    ldi r19,hi8(13108)
    sbrc r23,7
    rjmp .Lmean_base\@
    ldi r18,lo8(-13108)
    ldi r19,hi8(-13108)
.Lmean_base\@:
    add \oldlo,r18
    adc \oldhi,r19
    ldi r18,154
    ldi r19,25
    muls r23,r19
    movw \prodlo,r0
    mul r22,r18
    mov r21,r1
    mulsu r23,r18
    clr r18
    sbc \prodhi,r18
    add r21,r0
    adc \prodlo,r1
    adc \prodhi,r18
    mul r22,r19
    add r21,r0
    adc \prodlo,r1
    adc \prodhi,r18
    clr r1
    ldi r19,64
    add r21,r19
    adc \prodlo,r1
    adc \prodhi,r1
    lsl r21
    rol \prodlo
    rol \prodhi
    add \oldlo,\prodlo
    adc \oldhi,\prodhi
.endm
