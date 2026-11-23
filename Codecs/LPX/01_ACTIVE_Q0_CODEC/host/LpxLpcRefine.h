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
// The caller supplies complete safe, improving objective scores; nonfinite
// entries are ineligible. This helper only combines existing edits, never
// renders, scores or admits them. Keep every original single proposal too.
std::vector<Stream> composeLpcRuns(const Stream& anchor, const std::vector<Stream>& singles,
    const std::vector<double>& safeScores, int cap, bool finalV9Budget = false);
}
