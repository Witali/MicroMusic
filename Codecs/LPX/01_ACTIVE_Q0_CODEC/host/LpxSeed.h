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
struct LpxSeedContext {
    int h[10]={},ring[256]={},dd=0;
    double emphasized[48]={},residual[145]={};
    uint16_t previousVector[10]={};
    int16_t lastSample=0;
    bool continuation=false;
    int lookahead=0,accuracy=0;
    // Borrowed only during seedBegin: per-320-sample spectral safety strength.
    const uint8_t* spectralSafety=nullptr;
    const uint8_t* analysisOrder=nullptr;
};
int lpxSeedBeginContext(int samples,int profile,int rate,int pre,bool zeroScale,
                         double bandwidth,const LpxSeedContext* context);
LpxSeedView lpxSeedView();
uint32_t lpxSeedCapacity();
