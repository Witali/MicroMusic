/* Exact shared WB fold arithmetic. Input r21:r20, zero r2.
 * Q15 narrows floor(29491*x/32768) into r21:r20.
 * SCALE keeps only observable product bits 9..24, then alternates sign.
 * Four consecutive scratch registers a..d; coefficient scratch r18:r19.
 * Source macros avoid a call for every sample; C fallback: wb_fold.c. */
.macro WB_FOLD_Q15 a,b,c,d
    ldi r18,51
    ldi r19,115
    muls r19,r21
    movw \c,r0
    mul r18,r20
    movw \a,r0
    mulsu r19,r20
    sbc \d,r2
    add \b,r0
    adc \c,r1
    adc \d,r2
    mulsu r21,r18
    sbc \d,r2
    add \b,r0
    adc \c,r1
    adc \d,r2
    lsl \b
    rol \c
    rol \d
    movw r20,\c
.endm
.macro WB_FOLD_SCALE a,b,c,d,g0,g1,g2,g3,count
    mul r20,\g0
    movw \a,r0
    clr \c
    clr \d
    mul r21,\g0
    add \b,r0
    adc \c,r1
    adc \d,r2
    mul r20,\g1
    add \b,r0
    adc \c,r1
    adc \d,r2
    mul r21,\g1
    add \c,r0
    adc \d,r1
    mul r20,\g2
    add \c,r0
    adc \d,r1
    mul r21,\g2
    add \d,r0
    mul r20,\g3
    add \d,r0
    sbrs r21,7
    rjmp .Lfold_positive\@
    sub \c,\g0
    sbc \d,\g1
.Lfold_positive\@:
    ldi r18,1
    add \b,r18
    adc \c,r2
    adc \d,r2
    lsr \d
    ror \c
    ror \b
    sbrs \count,0
    rjmp .Lfold_store\@
    com \b
    com \c
    add \b,r18
    adc \c,r2
.Lfold_store\@:
.endm
