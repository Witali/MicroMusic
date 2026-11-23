#pragma once
#include "LpxAdaptive.h"
#include <limits>

namespace lpx {
struct LoudnessReport {
    // 0: not requested; 1: normalized; 2: shorter than 400 ms; 3: below gate.
    int status=0,limited=0;
    double input= -std::numeric_limits<double>::infinity();
    double prepared= -std::numeric_limits<double>::infinity();
    double decoded= -std::numeric_limits<double>::infinity();
    double gainDb=0;
};
// Mono BS.1770 integrated loudness, with complete 400 ms/100 ms gating blocks.
double integratedLoudness(const Pcm& pcm,int rate);
// One constant gain: -18 LUFS target, capped at -1 dBFS sample peak.
// Silence/below-gate and recordings shorter than 400 ms retain their PCM.
LoudnessReport normalizeLoudness(Pcm& pcm,int rate);
}
