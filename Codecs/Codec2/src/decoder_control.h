/* LGPL-2.1. Canonical control decisions from the frozen full float baseline.
 * Keep decoder_float.c unchanged as an independent regression baseline.
 */
#ifndef MICROMUSIC_CODEC2_DECODER_CONTROL_H
#define MICROMUSIC_CODEC2_DECODER_CONTROL_H
#include <stdint.h>
#include <string.h>
#include "defines.h"
static int harmonic_count(float wo) {
    /* AVR-GCC has 32-bit double, while the original native PI literal is
     * binary64. At minimum Wo, native truncation gives 79, AVR division 80.
     * One extra UV harmonic changes every later RNG draw. Compare the exact
     * binary32 mantissa product to the canonical PI threshold instead.
     * Wo's exponent is -5..-2 for every legal 3200 pitch/interpolation.
     */
    uint32_t bits;
    memcpy(&bits, &wo, sizeof(bits));
    int exponent = (int)((bits >> 23) & 255) - 127;
    uint32_t mantissa = (bits & UINT32_C(0x7fffff)) | UINT32_C(0x800000);
    uint32_t threshold = UINT32_C(3373259426) >> (7 + exponent); /* floor(PI*2^(23-exponent)) */
    int count = (int)(PI / wo);
    while ((uint32_t)count * mantissa > threshold) --count;
    while ((uint32_t)(count + 1) * mantissa <= threshold) ++count;
    return count;
}

static int band_boundary(int twice_harmonic, float wo, float radians_per_bin) {
    uint32_t wbits, rbits;
    memcpy(&wbits, &wo, sizeof(wbits));
    memcpy(&rbits, &radians_per_bin, sizeof(rbits));
    uint32_t wm = (wbits & UINT32_C(0x7fffff)) | UINT32_C(0x800000);
    uint32_t rm = (rbits & UINT32_C(0x7fffff)) | UINT32_C(0x800000);
    int shift = (int)((wbits >> 23) & 255) - (int)((rbits >> 23) & 255);
    uint64_t numerator = ((uint64_t)twice_harmonic * wm << shift) + rm;
    uint32_t denominator = 2 * rm;
    int count = (int)((0.5 * twice_harmonic) * wo / radians_per_bin + 0.5);
    /* Native uses binary64 for (m +/- .5)*Wo/r; AVR rounds it in binary32.
     * Exact dyadic-ratio comparisons stabilize half-bin control decisions.
     */
    while ((uint64_t)count * denominator > numerator) --count;
    while ((uint64_t)(count + 1) * denominator <= numerator) ++count;
    return count;
}

static int synthesis_bin(float harmonic_angle) {
    float scaled = harmonic_angle * 512;
    uint32_t bits;
    memcpy(&bits, &scaled, sizeof(bits));
    int exponent = (int)((bits >> 23) & 255) - 127;
    uint32_t mantissa = (bits & UINT32_C(0x7fffff)) | UINT32_C(0x800000);
    uint64_t exact = (uint64_t)mantissa << (exponent + 25); /* scaled * 2^48 */
    const uint64_t half_two_pi = UINT64_C(884279718978280); /* floor((6.283185307/2)*2^48) */
    int count = (int)(scaled / TWO_PI + 0.5);
    while (count > 0 && exact < (uint64_t)(2 * count - 1) * half_two_pi) --count;
    while (exact >= (uint64_t)(2 * count + 1) * half_two_pi) ++count;
    return count;
}

#endif
