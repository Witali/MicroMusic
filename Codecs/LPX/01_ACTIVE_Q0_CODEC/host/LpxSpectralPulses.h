#pragma once
#include "LpxAdaptive.h"

namespace lpx {
// Unguarded proposals only. The caller must evaluate complete decoded outputs
// against its protected incumbent with the common objective and safety rules.
struct SpectralPulseProposals {
    std::vector<Stream> proposals;
    uint64_t localEvaluations = 0;
    int regions = 0, changedPulses = 0;
};
// Fixed-width P4/P6 pulse changes; at most all/top-two/top-one region proposals.
// No decoder, gain, delay, spectrum, parameter or extra-pulse changes.
SpectralPulseProposals proposeSpectralPulses(const Stream& incumbent, const Pcm& reference);
}
