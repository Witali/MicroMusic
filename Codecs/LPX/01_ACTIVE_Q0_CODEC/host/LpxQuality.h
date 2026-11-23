#pragma once
#include "LpxAdaptive.h"
#include <limits>

namespace lpx {
struct Diagnostic {
    int within = 0, collapsed = 0;
    double period = std::numeric_limits<double>::quiet_NaN();
    double shape = std::numeric_limits<double>::quiet_NaN();
};
struct Quality {
    uint64_t error[2] = {};
    double stoi[2] = {std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::quiet_NaN()};
};
struct Measurement {
    Quality quality;
    Diagnostic diagnostic[2];
    double voice[2] = {}, noise[2] = {}, score = 0;
    int clipped = 0;
};
bool noRegression(const Quality& next, const Quality& baseline);
bool voiceGate(const Diagnostic& next, const Diagnostic& baseline);
class QualityContext {
public:
    // The default retains the original 8 kHz evaluator exactly. Other supported
    // rates (12/16 kHz) use antialiased double analysis, never rounded PCM.
    explicit QualityContext(const Pcm& reference, bool speech = true, int sampleRate = 8000);
    Quality quality(const Pcm& candidate) const;
    Measurement measure(const Pcm& candidate) const;
    const Pcm& reference;
private:
    bool speech;
    int sampleRate;
    std::vector<double> analysisReference;
    std::vector<double> periods, rms;
    void assess(const Pcm& candidate, double& voice, double& noise, Diagnostic& diagnostic) const;
};
// Testable numerical primitives; no file/network/host dependencies.
double estimatePeriod(const double* frame, int count, double& rms);
// Actual-rate version of the same estimator. Supports 8/12/16 kHz and at most
// 1280 samples; the three-argument legacy 8 kHz path remains unchanged.
double estimatePeriod(const double* frame, int count, double& rms, int sampleRate);
double stoi(const Pcm& reference, const Pcm& candidate, int sampleRate = 8000);
// PCM16-unit doubles, for source-frozen voice/noise analysis at 8 kHz.
// Supported input rates are 8, 12 and 16 kHz; unsupported rates return empty.
std::vector<double> qualityAnalysis8k(const Pcm& samples, int sampleRate);
void periodogram(const double* input, int count, double* power, int fftSize);
}
