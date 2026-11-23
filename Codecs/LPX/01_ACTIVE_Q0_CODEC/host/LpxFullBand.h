#pragma once
#include "LpxAdaptive.h"

namespace lpx {
// Native-rate diagnostic/admission view; independent of the legacy 8 kHz
// Measurement. The exact prospective rule is documented in full-band-quality.md.
struct FullBandMeasurement {
    bool valid = false;
    int bands = 0;
    double sourcePower[8] = {};
    bool supported[8] = {};
    double outputPower[2][8] = {}, error[2][8] = {}, retention[2][8] = {};
    double totalError[2] = {};
    // Source-referenced changes of each FFT magnitude between adjacent frames.
    // Per-band values use the same power units/normalization as error above.
    double temporalError[2][8] = {}, totalTemporalError[2] = {};
    double balancedError[2] = {}, balancedTemporalError[2] = {};
};
class FullBandContext {
public:
    FullBandContext(const Pcm& reference, int sampleRate);
    FullBandMeasurement measure(const Pcm& candidate) const;
    bool accepts(const FullBandMeasurement& next, const FullBandMeasurement& incumbent) const;
private:
    const Pcm& reference;
    int rate, bands = 0, frames = 0;
    double window[512], sourcePower[8] = {}, normalization = 0;
    void spectrum(const Pcm& samples, int start, double* power) const;
    int band(int bin) const;
};
}
