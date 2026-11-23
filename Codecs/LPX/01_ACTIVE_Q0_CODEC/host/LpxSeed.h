#pragma once
#include <stdint.h>

// Internal seed-search seam. Views are invalidated by reserve or another fit.
struct LpxSeedView {
    const uint8_t (*spectra)[10];
    const int (*params)[3];
    const int (*pulses)[2];
    const int16_t* pcm;
    bool valid;
};
int lpxSeedBegin(int samples, int profile, int rate, int pre, bool zeroScale,
                 double bandwidth = .97);
LpxSeedView lpxSeedView();
uint32_t lpxSeedCapacity();
