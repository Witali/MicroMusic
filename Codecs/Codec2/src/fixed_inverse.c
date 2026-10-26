/* Project adaptation of the pinned KISS real/radix-four inverse transform.
 * KISS copyright and complete BSD conditions accompany fixed_inverse_tables.inc.
 * Block floating-point C arithmetic; no assembly or forged architecture macros.
 */
#include "fixed_inverse.h"
#include "fixed_table_access.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#ifndef CODEC2_FIXED_BITS
#define CODEC2_FIXED_BITS 16
#endif
#ifndef CODEC2_FIXED_TWIDDLE_Q
#define CODEC2_FIXED_TWIDDLE_Q 9
#endif
#ifndef CODEC2_FIXED_WIDE_LAST
#define CODEC2_FIXED_WIDE_LAST 0
#endif
#ifndef CODEC2_FIXED_CHECKS
#define CODEC2_FIXED_CHECKS 0
#endif
#if CODEC2_FIXED_BITS == 8
typedef int8_t component;
#elif CODEC2_FIXED_BITS == 16
typedef int16_t component;
#elif CODEC2_FIXED_BITS == 24 || CODEC2_FIXED_BITS == 32
typedef int32_t component;
#else
#error Supported component precision is 8, 16, 24 or 32
#endif
#if CODEC2_FIXED_TWIDDLE_Q < 6 || CODEC2_FIXED_TWIDDLE_Q > 14
#error Supported twiddle precision is Q6 through Q14
#endif
#if CODEC2_FIXED_BITS <= 16
typedef int32_t product;
#else
typedef int64_t product;
#endif
typedef struct { component r, i; } complex_fixed;
typedef struct { int32_t r, i; } complex_wide;
typedef struct { int16_t r, i; } complex_twiddle;
typedef union {
    compact_transform floating;
    complex_fixed frequency[257];
    component time[514];
    complex_wide wide_frequency[257];
    int32_t wide_time[514];
} transform_fixed;
typedef char same_buffer_size[(sizeof(transform_fixed) == sizeof(compact_transform)) ? 1 : -1];
#include "fixed_inverse_tables.inc"

static int16_t sine(unsigned k) {
    k &= 511;
    unsigned index = k & 255;
    if (index > 128) index = 256 - index;
#if CODEC2_FIXED_TWIDDLE_Q == 6
    int16_t value = CODEC2_TABLE_BYTE(fixed_sine, index);
#else
    int16_t value = CODEC2_TABLE_WORD(fixed_sine, index);
#endif
    return k & 256 ? -value : value;
}

static complex_twiddle twiddle(unsigned k) {
    complex_twiddle result = {sine(k + 128), sine(k)};
    return result;
}

/* Symmetric nearest rounding; shifts operate only on nonnegative magnitudes. */
static product rounded(product value, unsigned bits) {
    if (!bits) return value;
    product half = (product)1 << (bits - 1);
    return value < 0 ? -((-value + half) >> bits) : (value + half) >> bits;
}

static component checked(product value) {
#if CODEC2_FIXED_CHECKS
    assert(value >= -((product)1 << (CODEC2_FIXED_BITS - 1)) && value < ((product)1 << (CODEC2_FIXED_BITS - 1)));
#endif
    return (component)value;
}

static uint32_t magnitude(component value) {
    uint32_t u = (uint32_t)value;
    return value < 0 ? UINT32_C(0) - u : u;
}

static complex_fixed multiply(complex_fixed value, complex_twiddle coefficient) {
    complex_fixed out;
    out.r = checked(rounded((product)value.r * coefficient.r - (product)value.i * coefficient.i, CODEC2_FIXED_TWIDDLE_Q));
    out.i = checked(rounded((product)value.r * coefficient.i + (product)value.i * coefficient.r, CODEC2_FIXED_TWIDDLE_Q));
    return out;
}

#if CODEC2_FIXED_BITS <= 24 && CODEC2_FIXED_WIDE_LAST
static complex_wide multiply_wide(complex_wide value, complex_twiddle coefficient) {
    complex_wide out;
    out.r = (int32_t)rounded((product)value.r * coefficient.r - (product)value.i * coefficient.i, CODEC2_FIXED_TWIDDLE_Q);
    out.i = (int32_t)rounded((product)value.r * coefficient.i + (product)value.i * coefficient.r, CODEC2_FIXED_TWIDDLE_Q);
    return out;
}
#endif

static unsigned normalize(complex_fixed *data) {
    uint32_t maximum = 0;
    const uint32_t limit = CODEC2_FIXED_BITS == 8 ? 24 : (UINT32_C(1) << (CODEC2_FIXED_BITS - 3)) / 16 * 15;
    for (unsigned i = 0; i < 256; ++i) {
        uint32_t norm = magnitude(data[i].r) + magnitude(data[i].i);
        if (norm > maximum) maximum = norm;
    }
    unsigned shift = 0;
    while (maximum > limit) { maximum = (maximum + 1) / 2; ++shift; }
    if (shift) for (unsigned i = 0; i < 256; ++i) {
        data[i].r = (component)rounded(data[i].r, shift);
        data[i].i = (component)rounded(data[i].i, shift);
    }
    return shift;
}

void codec2_fixed_inverse(compact_transform *buffer) {
    transform_fixed *fixed = (transform_fixed *)(void *)buffer;
    float maximum = 0;
    for (unsigned i = 0; i <= 256; ++i) {
        float norm = fabsf(buffer->frequency[i].r) + fabsf(buffer->frequency[i].i);
        if (norm > maximum) maximum = norm;
    }
    if (!maximum) { memset(buffer, 0, sizeof(*buffer)); return; }
    int exponent;
    frexpf(maximum, &exponent);
    exponent -= CODEC2_FIXED_BITS - 3;
    const uint32_t limit = CODEC2_FIXED_BITS == 8 ? 24 : (UINT32_C(1) << (CODEC2_FIXED_BITS - 3)) / 16 * 15;
    if (ldexpf(maximum, -exponent) > (float)limit) ++exponent;
    // The exponent reserves headroom for real preprocessing and the first stage.
    for (unsigned i = 0; i <= 256; ++i) {
        float r = ldexpf(buffer->frequency[i].r, -exponent);
        float im = ldexpf(buffer->frequency[i].i, -exponent);
        fixed->frequency[i].r = checked((product)(r < 0 ? r - .5f : r + .5f));
        fixed->frequency[i].i = checked((product)(im < 0 ? im - .5f : im + .5f));
    }
    complex_fixed dc = fixed->frequency[0], nyquist = fixed->frequency[256];
    fixed->frequency[0].r = checked((product)dc.r + nyquist.r);
    fixed->frequency[0].i = checked((product)dc.r - nyquist.r);
    for (unsigned k = 1; k <= 128; ++k) {
        complex_fixed first = fixed->frequency[k], second = fixed->frequency[256-k];
        second.i = (component)-second.i;
        complex_fixed even = {checked((product)first.r + second.r), checked((product)first.i + second.i)};
        complex_fixed difference = {checked((product)first.r - second.r), checked((product)first.i - second.i)};
        complex_fixed odd = multiply(difference, twiddle(128+k));
        fixed->frequency[k].r = checked((product)even.r + odd.r);
        fixed->frequency[k].i = checked((product)even.i + odd.i);
        fixed->frequency[256-k].r = checked((product)even.r - odd.r);
        fixed->frequency[256-k].i = checked(-((product)even.i - odd.i));
    }
    for (unsigned i = 0; i < 256; ++i) {
        unsigned j = ((i & 3) << 6) | ((i & 12) << 2) | ((i & 48) >> 2) | ((i & 192) >> 6);
        if (i < j) { complex_fixed t = fixed->frequency[i]; fixed->frequency[i] = fixed->frequency[j]; fixed->frequency[j] = t; }
    }
    for (unsigned size = 4; size <= (CODEC2_FIXED_BITS <= 24 && CODEC2_FIXED_WIDE_LAST ? 64 : 256); size *= 4) {
        exponent += normalize(fixed->frequency);
        unsigned m = size / 4, step = 512 / size;
        for (unsigned base = 0; base < 256; base += size) for (unsigned j = 0; j < m; ++j) {
            complex_fixed *out = fixed->frequency + base + j;
            complex_fixed b = multiply(out[m], twiddle(j*step));
            complex_fixed c = multiply(out[2*m], twiddle(2*j*step));
            complex_fixed d = multiply(out[3*m], twiddle(3*j*step));
            product ar = out[0].r, ai = out[0].i;
            out[0].r = checked(ar + c.r + ((product)b.r + d.r));
            out[0].i = checked(ai + c.i + ((product)b.i + d.i));
            out[2*m].r = checked(ar + c.r - ((product)b.r + d.r));
            out[2*m].i = checked(ai + c.i - ((product)b.i + d.i));
            out[m].r = checked(ar - c.r - ((product)b.i - d.i));
            out[m].i = checked(ai - c.i + ((product)b.r - d.r));
            out[3*m].r = checked(ar - c.r + ((product)b.i - d.i));
            out[3*m].i = checked(ai - c.i - ((product)b.r - d.r));
        }
    }
#if CODEC2_FIXED_BITS <= 24 && CODEC2_FIXED_WIDE_LAST
    /* The final radix-four output needs two more magnitude bits. Expand into
     * the existing float-sized bank instead of discarding those bits through
     * another global normalization. Earlier stages retain narrow storage.
     */
    for (int i = 255; i >= 0; --i) {
        component r = fixed->frequency[i].r, im = fixed->frequency[i].i;
        fixed->wide_frequency[i].r = r; fixed->wide_frequency[i].i = im;
    }
    for (unsigned j = 0; j < 64; ++j) {
        complex_wide *out = fixed->wide_frequency + j;
        complex_wide b = multiply_wide(out[64], twiddle(2*j));
        complex_wide c = multiply_wide(out[128], twiddle(4*j));
        complex_wide d = multiply_wide(out[192], twiddle(6*j));
        int32_t ar = out[0].r, ai = out[0].i;
        out[0].r = ar + c.r + (b.r + d.r); out[0].i = ai + c.i + (b.i + d.i);
        out[128].r = ar + c.r - (b.r + d.r); out[128].i = ai + c.i - (b.i + d.i);
        out[64].r = ar - c.r - (b.i - d.i); out[64].i = ai - c.i + (b.r - d.r);
        out[192].r = ar - c.r + (b.i - d.i); out[192].i = ai - c.i - (b.r - d.r);
    }
    for (int i = 511; i >= 0; --i) buffer->time[i] = ldexpf((float)fixed->wide_time[i], exponent);
#else
    // Expand from the end: 8/16-bit packed samples share storage with floats.
    for (int i = 511; i >= 0; --i) buffer->time[i] = ldexpf((float)fixed->time[i], exponent);
#endif
}
