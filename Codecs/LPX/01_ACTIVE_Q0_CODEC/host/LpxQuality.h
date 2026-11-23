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
    explicit QualityContext(const Pcm& reference, bool speech = true);
    Quality quality(const Pcm& candidate) const;
    Measurement measure(const Pcm& candidate) const;
    const Pcm& reference;
private:
    bool speech;
    std::vector<double> periods, rms;
    void assess(const Pcm& candidate, double& voice, double& noise, Diagnostic& diagnostic) const;
};
// Testable numerical primitives; no file/network/host dependencies.
double estimatePeriod(const double* frame, int count, double& rms);
double stoi(const Pcm& reference, const Pcm& candidate);
void periodogram(const double* input, int count, double* power, int fftSize);
}
