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

static SPEEX_NB3_STAGE void speex_nb3_interpolate(
    int16_t *restrict raw, const int16_t *restrict delta, int16_t *restrict out)
{
    unsigned i;
    int16_t previous, current, following;
    raw[0] += delta[0];
    previous = raw[0] < 16 ? 16 : raw[0];
    out[0] = previous;
    current = raw[1] + delta[1];
    for (i = 1; i < 9; i++) {
        int next;
        raw[i] = current;
        following = raw[i+1] + delta[i+1];
        /* Upstream clamps element 9 before adjusting elements 1..8. */
        next = (i == 8 && following > 25720) ? 25720 : following;
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
    out[9] = current > 25720 ? 25720 : current;
}
#endif
