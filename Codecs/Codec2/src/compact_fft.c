/*
Copyright (c) 2003-2010, Mark Borgerding
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:
 * Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
 * Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
 * Neither the author nor the names of any contributors may be used to endorse
   or promote products derived from this software without specific prior
   written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
OF THE POSSIBILITY OF SUCH DAMAGE.
*/
/* Project adaptation of pinned KISS radix-four and real-FFT operations:
 * fixed N=512 real / N=256 complex, ROM twiddles, one in-place buffer.
 * Input/output operation order follows the original scalar float butterflies.
 */
#include "compact_fft.h"
#include "float_table_access.h"
#include "compact_tables.inc"
#include <stdint.h>
#include <string.h>

#define ADD(c,a,b) do { (c).r=(a).r+(b).r; (c).i=(a).i+(b).i; } while (0)
#define SUB(c,a,b) do { (c).r=(a).r-(b).r; (c).i=(a).i-(b).i; } while (0)
#define MUL(c,a,b) do { (c).r=(a).r*(b).r-(a).i*(b).i; (c).i=(a).r*(b).i+(a).i*(b).r; } while (0)

static compact_complex twiddle(unsigned index, int inverse) {
    compact_complex value;
    value.r = CODEC2_TABLE_FLOAT(compact_twiddle, 2 * index);
    value.i = CODEC2_TABLE_FLOAT(compact_twiddle, 2 * index + 1);
    if (inverse) value.i = -value.i;
    return value;
}

static compact_complex super_twiddle(unsigned index, int inverse) {
    compact_complex value;
    value.r = CODEC2_TABLE_FLOAT(compact_super, 2 * index);
    value.i = CODEC2_TABLE_FLOAT(compact_super, 2 * index + 1);
    if (inverse) value.i = -value.i;
    return value;
}

static uint8_t reverse_four(uint8_t x) {
    return (uint8_t)(((x & 3) << 6) | ((x & 12) << 2) | ((x & 48) >> 2) | ((x & 192) >> 6));
}

static void fft256(compact_complex *buffer, int inverse) {
    for (unsigned size = 4; size <= 256; size *= 4) {
        unsigned m = size / 4, step = 256 / size;
        for (unsigned base = 0; base < 256; base += size) {
            for (unsigned j = 0; j < m; ++j) {
                compact_complex *out = buffer + base + j;
                compact_complex s[6], tw;
                tw = twiddle(j * step, inverse); MUL(s[0], out[m], tw);
                tw = twiddle(2 * j * step, inverse); MUL(s[1], out[2 * m], tw);
                tw = twiddle(3 * j * step, inverse); MUL(s[2], out[3 * m], tw);
                SUB(s[5], out[0], s[1]);
                out[0].r += s[1].r; out[0].i += s[1].i;
                ADD(s[3], s[0], s[2]); SUB(s[4], s[0], s[2]);
                SUB(out[2 * m], out[0], s[3]);
                out[0].r += s[3].r; out[0].i += s[3].i;
                if (inverse) {
                    out[m].r = s[5].r - s[4].i; out[m].i = s[5].i + s[4].r;
                    out[3 * m].r = s[5].r + s[4].i; out[3 * m].i = s[5].i - s[4].r;
                } else {
                    out[m].r = s[5].r + s[4].i; out[m].i = s[5].i - s[4].r;
                    out[3 * m].r = s[5].r - s[4].i; out[3 * m].i = s[5].i + s[4].r;
                }
            }
        }
    }
}

static void real_pair(compact_complex first, compact_complex conjugate_second,
                      unsigned k, compact_complex *positive, compact_complex *negative) {
    compact_complex sum, difference, product, tw = super_twiddle(k - 1, 0);
    ADD(sum, first, conjugate_second); SUB(difference, first, conjugate_second);
    MUL(product, difference, tw);
    positive->r = (sum.r + product.r) * .5;
    positive->i = (sum.i + product.i) * .5;
    negative->r = (sum.r - product.r) * .5;
    negative->i = (product.i - sum.i) * .5;
}

void compact_forward_lpc(compact_transform *buffer, const float coefficients[11]) {
    memset(buffer, 0, sizeof(*buffer));
    for (unsigned i = 0; i < 6; ++i) {
        unsigned at = reverse_four((uint8_t)i);
        buffer->frequency[at].r = coefficients[2 * i];
        buffer->frequency[at].i = i < 5 ? coefficients[2 * i + 1] : 0;
    }
    fft256(buffer->frequency, 0);
    compact_complex dc = buffer->frequency[0];
    buffer->frequency[0].r = dc.r + dc.i; buffer->frequency[0].i = 0;
    buffer->frequency[256].r = dc.r - dc.i; buffer->frequency[256].i = 0;
    for (unsigned k = 1; k <= 128; ++k) {
        compact_complex first = buffer->frequency[k], second = buffer->frequency[256 - k];
        second.i = -second.i;
        real_pair(first, second, k, &buffer->frequency[k], &buffer->frequency[256 - k]);
    }
}

/* Select the original radix-four output without changing its arithmetic DAG. */
static compact_complex select_four(compact_complex a, compact_complex b,
                                   compact_complex c, compact_complex d,
                                   unsigned j, unsigned step, unsigned which) {
    compact_complex s[6], tw, result;
    tw = twiddle(j * step, 0); MUL(s[0], b, tw);
    tw = twiddle(2 * j * step, 0); MUL(s[1], c, tw);
    tw = twiddle(3 * j * step, 0); MUL(s[2], d, tw);
    SUB(s[5], a, s[1]); a.r += s[1].r; a.i += s[1].i;
    ADD(s[3], s[0], s[2]); SUB(s[4], s[0], s[2]);
    if (which == 0) { ADD(result, a, s[3]); }
    else if (which == 2) { SUB(result, a, s[3]); }
    else if (which == 1) { result.r = s[5].r + s[4].i; result.i = s[5].i - s[4].r; }
    else { result.r = s[5].r - s[4].i; result.i = s[5].i + s[4].r; }
    return result;
}

static compact_complex sparse_complex(const float a[11], unsigned bin) {
    compact_complex zero = {0, 0};
    compact_complex c0 = {a[0], a[1]}, c1 = {a[2], a[3]};
    compact_complex c2 = {a[4], a[5]}, c3 = {a[6], a[7]};
    compact_complex c4 = {a[8], a[9]}, c5 = {a[10], 0};
    unsigned low = bin & 63;
    /* All N=4/N=16 children contain one nonzero element. N=64 children
     * 0 and 1 contain two; 2 and 3 contain one. Keep the two remaining
     * N=64 butterflies and the root N=256 butterfly in original order.
     */
    compact_complex first = select_four(c0, c4, zero, zero, low & 15, 4, low >> 4);
    compact_complex second = select_four(c1, c5, zero, zero, low & 15, 4, low >> 4);
    return select_four(first, second, c2, c3, bin & 63, 1, bin >> 6);
}

compact_complex compact_sparse_lpc_bin(const float coefficients[11], unsigned bin) {
    if (bin == 0 || bin == 256) {
        compact_complex dc = sparse_complex(coefficients, 0), result;
        result.r = bin == 0 ? dc.r + dc.i : dc.r - dc.i;
        result.i = 0;
        return result;
    }
    unsigned k = bin < 128 ? bin : 256 - bin;
    compact_complex first = sparse_complex(coefficients, k);
    compact_complex second = sparse_complex(coefficients, 256 - k);
    compact_complex positive, negative;
    second.i = -second.i;
    real_pair(first, second, k, &positive, &negative);
    /* k=128 aliases both outputs in original KISS; the negative write wins. */
    return bin < 128 ? positive : negative;
}

void compact_inverse(compact_transform *buffer) {
    compact_complex dc = buffer->frequency[0], nyquist = buffer->frequency[256];
    buffer->frequency[0].r = dc.r + nyquist.r;
    buffer->frequency[0].i = dc.r - nyquist.r;
    for (unsigned k = 1; k <= 128; ++k) {
        compact_complex first = buffer->frequency[k], second = buffer->frequency[256 - k];
        compact_complex even, odd, difference, tw = super_twiddle(k - 1, 1);
        second.i = -second.i;
        ADD(even, first, second); SUB(difference, first, second); MUL(odd, difference, tw);
        ADD(buffer->frequency[k], even, odd);
        SUB(buffer->frequency[256 - k], even, odd);
        buffer->frequency[256 - k].i *= -1;
    }
    for (unsigned i = 0; i < 256; ++i) {
        unsigned j = reverse_four((uint8_t)i);
        if (i < j) {
            compact_complex temp = buffer->frequency[i];
            buffer->frequency[i] = buffer->frequency[j]; buffer->frequency[j] = temp;
        }
    }
    fft256(buffer->frequency, 1);
}

float compact_window_value(unsigned index) {
    return CODEC2_TABLE_FLOAT(compact_window, index);
}
