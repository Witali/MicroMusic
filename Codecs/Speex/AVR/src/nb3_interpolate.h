/* Four-quarter NB3 LSP interpolation, specialized for order 10 / margin 16.
 * The sequential margin pass follows Xiph Speex 1.2.1 lsp.c:
 * Copyright (C) 2002-2006 Jean-Marc Valin; BSD terms in vendor/.../COPYING.
 * Raw endpoint angles from the pinned NB3 codebooks are multiples of 16.
 * Thus each separately rounded upstream Q14 product is already integral:
 * old + (sub+1) * ((next>>2) - (old>>2)) gives the same raw interpolation.
 * The caller computes delta once and calls four times on a changed frame.
 * On reset it uses zero deltas and calls once; cached frames need no call.
 * raw, delta and out must be distinct arrays of ten int16_t elements.
 * raw advances in place, remaining separate from the margin-adjusted output;
 * after four calls it equals the new endpoint, without a final frame copy.
 * C implementation for every arithmetic backend, including AVR ASM builds. */
#ifndef SPEEX_NB3_INTERPOLATE_H
#define SPEEX_NB3_INTERPOLATE_H
#include "speex_platform.h"

static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_interpolate_core(
    int16_t *restrict raw, const int16_t *restrict delta, int16_t *restrict out, uint8_t bounded)
{
    unsigned i;
    int16_t previous, current, following;
    raw[0] += delta[0];
    previous = bounded ? raw[0] : (raw[0] < 16 ? 16 : raw[0]);
    out[0] = previous;
    current = raw[1] + delta[1];
    for (i = 1; i < 9; i++) {
        int next;
        raw[i] = current;
        following = raw[i+1] + delta[i+1];
        /* Upstream clamps element 9 before adjusting elements 1..8. */
        next = (!bounded && i == 8 && following > 25720) ? 25720 : following;
        if (current < previous + 16) current = previous + 16;
        /* Retain both shifts: combining them into one average can round
         * differently after an earlier margin correction made an odd angle.
         * Keep next as int to retain the upstream integer promotions. */
        if (current > next - 16) current = (current >> 1) + ((next - 16) >> 1);
        out[i] = current;
        previous = current;
        current = following;
    }
    raw[9] = current;
    out[9] = bounded ? current : (current > 25720 ? 25720 : current);
}

/* Retain the general signed16/multiple-of-16 endpoint contract for callers
 * and tests that deliberately exercise values outside the NB3 codebooks. */
static SPEEX_NB3_STAGE void speex_nb3_interpolate(
    int16_t *restrict raw, const int16_t *restrict delta, int16_t *restrict out)
{
    speex_nb3_interpolate_core(raw,delta,out,0);
}

/* Private fast path: updated raw[0] >= 16 and raw[9] <= 25720, with all
 * updated values representable in signed16. Every pinned NB3 endpoint is
 * in [96,24880]; convex quarter steps preserve that range. Reset initializes
 * raw from a real endpoint before its zero-delta call. Endpoint clamps and
 * the last lookahead clamp are therefore redundant; interior sequential
 * margins, both half-shifts and the separate raw state remain unchanged.
 * A constant flag is folded into this single-callsite C implementation. */
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_interpolate_validated(
    int16_t *restrict raw, const int16_t *restrict delta, int16_t *restrict out)
{
    speex_nb3_interpolate_core(raw,delta,out,1);
}

/* Private NB3 codebook domain, stronger than the bounded helper above:
 * raw+delta is a convex quarter-step of the pinned codebook endpoints and
 * is a multiple of four. Affine certificates in reports/margin-proof.json
 * prove only two central repairs can occur, and they are mutually exclusive.
 * Both average inputs are even; a+(b-16) <=27968 and b+(c-16) <=32720.
 * A single signed16 sum/shift is therefore exact here. General callers must
 * retain the two separately rounded halves in the helpers above. */
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_repair_center_c(
    int16_t a,int16_t b,int16_t c,int16_t *out)
{
    if(a>b-16){a=(a+(b-16))>>1;b=a+16;}
    else if(b>c-16){b=(b+(c-16))>>1;c=b+16;}
    out[0]=a;out[1]=b;out[2]=c;
}

/* C decoder path: raw/delta/out are distinct ten-word arrays. Values outside
 * positions 3..5 need no margin correction in the pinned codebook domain. */
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_interpolate_codebook(
    int16_t *restrict raw,const int16_t *restrict delta,int16_t *restrict out)
{
    raw[0]+=delta[0];out[0]=raw[0];
    raw[1]+=delta[1];out[1]=raw[1];
    raw[2]+=delta[2];out[2]=raw[2];
    raw[3]+=delta[3];raw[4]+=delta[4];raw[5]+=delta[5];
    raw[6]+=delta[6];out[6]=raw[6];
    raw[7]+=delta[7];out[7]=raw[7];
    raw[8]+=delta[8];out[8]=raw[8];
    raw[9]+=delta[9];out[9]=raw[9];
    speex_nb3_repair_center_c(raw[3],raw[4],raw[5],out+3);
}

/* Ten raw updates and only three corrected center angles. The fused LPC
 * converter temporarily stores these in its dead output slot. Keep this C
 * implementation available on AVR too, independently of ASM selection. */
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_advance_codebook_c(
    int16_t *restrict raw,const int16_t *restrict delta,int16_t *restrict center)
{
    for(unsigned i=0;i<10;i++)raw[i]+=delta[i];
    speex_nb3_repair_center_c(raw[3],raw[4],raw[5],center);
}
#if SPEEX_NB3_USE_AVR_ASM
extern void speex_avr_nb3_advance10(int16_t *,const int16_t *,int16_t *);
#endif
static SPEEX_NB3_ALWAYS_INLINE void speex_nb3_advance_codebook(
    int16_t *restrict raw,const int16_t *restrict delta,int16_t *restrict center)
{
#if SPEEX_NB3_USE_AVR_ASM
    speex_avr_nb3_advance10(raw,delta,center);
#else
    speex_nb3_advance_codebook_c(raw,delta,center);
#endif
}
void speex_nb3_interpolate_lpc(int16_t *restrict,const int16_t *restrict,int16_t *restrict);
#endif
