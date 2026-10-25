/* ATmega328P/GNU ABI: raw r25:r24, delta r23:r22, center r21:r20.
 * Ten signed16 updates; return corrected frequencies 3..5 in center[3].
 * Codebook/quarter constraints prove positive sums <=32720 and exclude
 * simultaneous repairs. Raw/delta/center are disjoint RAM arrays: read/write
 * 20 raw bytes, read 20 delta bytes, write six center bytes. Enhanced AVR5
 * instructions (MOVW/LDD); no hardware registers, MUL, CLI or RAM scratch.
 * Only r0/r1, r18..r27 and r30/r31 change; r2..r17/Y stay intact, r1 is zero
 * at RET. C fallback/explicit opt-in: nb3_interpolate.h. Geometry/provenance:
 * tools/prove_nb3_margins.py and vendor/speex-1.2.1/COPYING. */
.section .text.speex_avr_nb3_advance10,"ax",@progbits
.global speex_avr_nb3_advance10
.type speex_avr_nb3_advance10,@function
.macro NB3_UPDATE_WORD
    ld r18,Z
    ldd r19,Z+1
    ld r0,X+
    ld r1,X+
    add r18,r0
    adc r19,r1
    st Z+,r18
    st Z+,r19
.endm
speex_avr_nb3_advance10:
    movw r30,r24
    movw r26,r22
    movw r24,r20
    NB3_UPDATE_WORD
    NB3_UPDATE_WORD
    NB3_UPDATE_WORD
    NB3_UPDATE_WORD
    movw r20,r18
    NB3_UPDATE_WORD
    movw r22,r18
    NB3_UPDATE_WORD
    subi r22,16
    sbci r23,0
    cp r22,r20
    cpc r23,r21
    brsh .Lnb3_first_ok
    add r20,r22
    adc r21,r23
    lsr r21
    ror r20
    movw r22,r20
    subi r22,lo8(-16)
    sbci r23,hi8(-16)
    rjmp .Lnb3_store
.Lnb3_first_ok:
    subi r22,lo8(-16)
    sbci r23,hi8(-16)
    subi r18,16
    sbci r19,0
    cp r18,r22
    cpc r19,r23
    brsh .Lnb3_second_ok
    add r22,r18
    adc r23,r19
    lsr r23
    ror r22
    movw r18,r22
    subi r18,lo8(-16)
    sbci r19,hi8(-16)
    rjmp .Lnb3_store
.Lnb3_second_ok:
    subi r18,lo8(-16)
    sbci r19,0xff
.Lnb3_store:
    movw r0,r26
    movw r26,r24
    st X+,r20
    st X+,r21
    st X+,r22
    st X+,r23
    st X+,r18
    st X+,r19
    movw r26,r0
    NB3_UPDATE_WORD
    NB3_UPDATE_WORD
    NB3_UPDATE_WORD
    NB3_UPDATE_WORD
    clr r1
    ret
.size speex_avr_nb3_advance10,.-speex_avr_nb3_advance10
