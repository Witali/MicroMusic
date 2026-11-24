#pragma once
#include "LpxAdaptive.h"
#include <initializer_list>

// Selectable previous encoder for reproducible comparisons, independently of
// CPU, CUDA, or SIMD arithmetic selection. The decoder is unaffected.
#ifndef LPX_ENCODER_QUALITY_SEARCH
#define LPX_ENCODER_QUALITY_SEARCH 1
#endif
#ifndef LPX_ENCODER_SPECTRAL_PULSES
#define LPX_ENCODER_SPECTRAL_PULSES 1
#endif
#ifndef LPX_ENCODER_JOINT_REFINEMENT
#define LPX_ENCODER_JOINT_REFINEMENT 1
#endif
#ifndef LPX_ENCODER_LPC_RUNS
#define LPX_ENCODER_LPC_RUNS 1
#endif

namespace lpx {
class CandidateEvaluation;
struct ProfileQualityReport {
    int candidates = 0, accepted = 0, error = 0, octaveRejected = 0;
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
    bool speech = true,CandidateEvaluation* evaluation=nullptr);
struct JointQualityReport {
    // This phase has its own frozen incumbent: the complete previous V3 winner.
    // These relative scores must not be multiplied by earlier phase scores.
    ProfileQualityReport selection;
    int headerLocalEvaluations = 0;
    int headerFullEvaluations = 0, lpcRuns = 0, lpcProposals = 0, lpcBundles = 0;
    uint64_t lpcSpectralEvaluations = 0, lpcPulseEvaluations = 0;
    uint64_t lpcSynthesizedSamples = 0;
};
// Protected continuation of the exact existing V3 quality phase. Generic
// profiles get LPC-run proposals; strict3k also gets existing header proposals.
// Budget semantics match refineProfileQuality; never adds decoder side data.
// A disabled incumbent brightness filter stays disabled.
Stream refineJointQuality(const Stream& incumbent, const Pcm& reference,
    int cap, bool finalV9Budget, JointQualityReport& report, bool threeK = false,
    bool speech = true,CandidateEvaluation* evaluation=nullptr);
// Same frozen whole-output safety/objective for a finalized streaming proposal.
bool profileQualityAdmission(const Pcm& reference,const Pcm& incumbent,
                             const Pcm& candidate,int sampleRate,bool speech=true,bool strictlyBetter=false);
// Compare completed proposals against one immutable floor, never a chain of
// relative scores. A tie retains that floor, even if a proposal is smaller.
Stream selectQualityProposals(const Stream& incumbent,const Pcm& reference,
    std::initializer_list<const Stream*> proposals,ProfileQualityReport& report,
    bool speech=true,int completeV9Budget=0,CandidateEvaluation* evaluation=nullptr);
}
