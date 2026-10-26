#include "fixed_inverse.h"
#include "kiss_fftr.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>

static uint32_t random_state = 1;
static float next(void) {
    random_state = random_state * UINT32_C(1664525) + UINT32_C(1013904223);
    return ((int32_t)(random_state >> 8) - 8388608) / 8388608.0f;
}

int main(void) {
    kiss_fftr_cfg inverse = kiss_fftr_alloc(512, 1, NULL, NULL);
    assert(inverse);
    double signal = 0, noise = 0, maximum_relative = 0;
    for (unsigned trial = 0; trial < 512; ++trial) {
        compact_transform output;
        kiss_fft_cpx input[257];
        float expected[512];
        float scale = ldexpf(1.0f, (int)(trial % 33) - 16);
        for (unsigned k = 0; k <= 256; ++k) {
            float real = trial < 257 ? (float)(k == trial) : next();
            float imag = trial < 257 ? 0 : next();
            input[k].r = output.frequency[k].r = real * scale;
            input[k].i = output.frequency[k].i = imag * scale;
        }
        kiss_fftri(inverse, input, expected);
        codec2_fixed_inverse(&output);
        for (unsigned i = 0; i < 512; ++i) {
            double value = output.time[i] / scale, reference = expected[i] / scale;
            double error = value - reference;
            signal += reference * reference; noise += error * error;
            if (fabs(error) > maximum_relative) maximum_relative = fabs(error);
        }
    }
    kiss_fftr_free(inverse);
    printf("{\"vectors\":512,\"snr_db\":%.9g,\"maximum_error_per_input_scale\":%.9g}\n", 10*log10(signal/noise), maximum_relative);
    return 0;
}
