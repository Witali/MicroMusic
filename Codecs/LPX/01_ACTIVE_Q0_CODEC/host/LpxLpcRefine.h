#pragma once
#include "LpxAdaptive.h"

namespace lpx {
// Unguarded, complete-stream proposals. The caller retains the previous winner
// and applies its common whole-output objective, safety rules and real cap.
struct LpcRunProposals {
    std::vector<Stream> proposals;
    uint64_t spectralEvaluations = 0, pulseEvaluations = 0, synthesizedSamples = 0;
    int runs = 0;
};
// Edit a whole equal-spectrum run, preserving its internal repeat coding.
// At most four runs and eight raw/joint proposals; no decoder/header extension.
LpcRunProposals proposeLpcRuns(const Stream& incumbent, const Pcm& reference,
                             int cap, bool finalV9Budget = false);
}
