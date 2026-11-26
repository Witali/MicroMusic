#pragma once
#include "LpxAdaptive.h"
#include <cstddef>

namespace lpx {
// Conservative observation-level floor, not a fundamental-frequency oracle.
// Fixed source windows and the exact complete incumbent's octave labels are
// cached once. No loss weights, new thresholds or decoder state are added.
class PitchGuardContext {
public:
    PitchGuardContext(const Pcm& reference, const Pcm& incumbent, int sampleRate,
                      QualityTarget target = QualityTarget::Pwm);
    bool accepts(const Pcm& candidate) const;
private:
    const QualityTarget target;
    bool valid = false;
    int rate, frame, hop;
    std::size_t samples;
    std::vector<double> sourcePeriods;
    std::vector<uint8_t> baselineMasks[2];
};
}
