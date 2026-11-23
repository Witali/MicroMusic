#pragma once
#include "LpxAdaptive.h"

// Selectable previous encoder for reproducible comparisons, independently of
// CPU, CUDA, or SIMD arithmetic selection. The decoder is unaffected.
#ifndef LPX_ENCODER_QUALITY_SEARCH
#define LPX_ENCODER_QUALITY_SEARCH 1
#endif
#ifndef LPX_ENCODER_SPECTRAL_PULSES
#define LPX_ENCODER_SPECTRAL_PULSES 1
#endif

namespace lpx {
struct ProfileQualityReport {
    int candidates = 0, accepted = 0, error = 0;
    int bandwidthCandidates = 0, localEvaluations = 0, fullEvaluations = 0;
    uint64_t spectralLocalEvaluations = 0;
    int spectralProposals = 0, spectralRegions = 0;
    double initialObjective = 0, finalObjective = 0;
};
// Bounded post-search proposals protect the complete prior selected stream.
// cap is the existing full v5 budget unless finalV9Budget is true. threeK
// selects the existing strict-3k spectral allocator, never a new wire format.
Stream refineProfileQuality(const Stream& incumbent, const Pcm& reference,
    int cap, bool finalV9Budget, ProfileQualityReport& report, bool threeK = false,
    bool speech = true);
// Same frozen whole-output safety/objective for a finalized streaming proposal.
bool profileQualityAdmission(const Pcm& reference,const Pcm& incumbent,
                             const Pcm& candidate,int sampleRate,bool speech=true);
}
