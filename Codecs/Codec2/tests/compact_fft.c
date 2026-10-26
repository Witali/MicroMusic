#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "compact_fft.h"
#include "kiss_fftr.h"

static uint32_t seed = 1;
static float sample(void) {
    seed = seed * UINT32_C(1664525) + UINT32_C(1013904223);
    return ((int32_t)(seed >> 8) - 8388608) / 65536.0f;
}

int main(void) {
    kiss_fftr_cfg forward = kiss_fftr_alloc(512, 0, NULL, NULL);
    kiss_fftr_cfg inverse = kiss_fftr_alloc(512, 1, NULL, NULL);
    assert(forward && inverse);
    for (unsigned trial = 0; trial < 512; ++trial) {
        float coefficients[11], input[512] = {0}, expected_time[512];
        kiss_fft_cpx expected[257];
        compact_transform compact;
        for (unsigned i = 0; i < 11; ++i) coefficients[i] = trial < 11 ? (float)(i == trial) : sample();
        memcpy(input, coefficients, sizeof(coefficients));
        kiss_fftr(forward, input, expected);
        compact_forward_lpc(&compact, coefficients);
        for (unsigned bin = 0; bin <= 256; ++bin) {
            compact_complex sparse = compact_sparse_lpc_bin(coefficients, bin);
            if (compact.frequency[bin].r != expected[bin].r || compact.frequency[bin].i != expected[bin].i
                || sparse.r != expected[bin].r || sparse.i != expected[bin].i) {
                fprintf(stderr, "FFT mismatch trial=%u bin=%u expected=(%a,%a) dense=(%a,%a) sparse=(%a,%a)\n",
                    trial, bin, expected[bin].r, expected[bin].i, compact.frequency[bin].r,
                    compact.frequency[bin].i, sparse.r, sparse.i);
                return 1;
            }
        }
        for (unsigned k = 1; k <= 128; ++k) {
            compact_complex positive, negative;
            compact_sparse_lpc_pair(coefficients, k, &positive, &negative);
            assert(k == 128 || (positive.r == expected[k].r && positive.i == expected[k].i));
            assert(negative.r == expected[256 - k].r && negative.i == expected[256 - k].i);
        }
        for (unsigned bin = 0; bin <= 256; ++bin) {
            expected[bin].r = sample(); expected[bin].i = sample();
            compact.frequency[bin].r = expected[bin].r; compact.frequency[bin].i = expected[bin].i;
        }
        kiss_fftri(inverse, expected, expected_time);
        compact_inverse(&compact);
        for (unsigned i = 0; i < 512; ++i) {
            if (compact.time[i] != expected_time[i]) {
                fprintf(stderr, "IFFT mismatch trial=%u sample=%u expected=%a actual=%a\n", trial, i, expected_time[i], compact.time[i]);
                return 1;
            }
        }
    }
    kiss_fftr_free(forward); kiss_fftr_free(inverse);
    puts("PASS: 512 LPC vectors/all 257 bins, sparse and in-place forward; 512 dense inverse vectors match original KISS float values");
    return 0;
}
