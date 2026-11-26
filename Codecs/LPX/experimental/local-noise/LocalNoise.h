#pragma once
#include "LpxAdaptive.h"
#include "LpxProfileQuality.h"
#include <array>
#include <limits>

namespace lpx {
// Prospective experiment constants. None are selected from benchmark outcomes.
namespace localnoise {
static const char Version[] = "local-noise-v1";
enum { FftSamples=512, HopSamples=256, ScoreWindows=3, MaxRegions=4,
       PairsPerRegion=4, SseShortlist=8, MaxFirstChoices=4, MaxHorizon=808 };
static constexpr double QuietRms=64., MinPeriodicity=.75,
    MaxSliceEnergyRatio=4., MinHarmonicFraction=.70, NoiseWeight=2.;
}

struct LocalNoiseWindow {
    int start=0;
    bool supported=false, quiet=false, transient=false, voiced=false;
    double period=std::numeric_limits<double>::quiet_NaN();
    double periodicity=0, harmonicFraction=0, normalization=0;
    // One means outside the frozen source harmonic neighborhoods. All zeros
    // for unsupported, quiet, transient or unvoiced windows; DC is always zero.
    std::array<uint8_t,257> interharmonic={};
    std::array<double,257> sourceMagnitude={};
};
struct LocalNoiseMeasurement {
    QualityTarget target=QualityTarget::Pwm;
    bool valid=false;
    int windows=0, voicedWindows=0, quietWindows=0, transientWindows=0, unsupportedWindows=0;
    double magnitude[2]={std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::quiet_NaN()};
    double interharmonic[2]={std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::quiet_NaN()};
    double score=std::numeric_limits<double>::quiet_NaN();
};
// Source masks, periods, energy floors and harmonic neighborhoods are computed
// once. Candidate samples cannot mutate this analysis or select another F0.
class LocalNoiseContext {
    const Pcm& reference;
    std::vector<LocalNoiseWindow> descriptors;
public:
    const int rate;
    const QualityTarget target;
    LocalNoiseContext(const Pcm& reference,int sampleRate,QualityTarget target);
    LocalNoiseMeasurement measure(const Pcm& candidate) const;
    const std::vector<LocalNoiseWindow>& analysis() const { return descriptors; }
};

struct LocalNoiseReport {
    int error=0, regions=0, pairs=0, proposals=0, fullEvaluations=0;
    int noiseProposals=0, sseProposals=0, noisePatches=0, ssePatches=0;
    int admittedNoiseProposals=0, admittedSseProposals=0;
    int accepted=0, selectedNoise=0, selectedSse=0;
    // Local candidate forward renders and their SSE scores. The sample count
    // excludes original-prefix recovery and complete raw/admission renders;
    // external elapsed time measures the complete experimental refinement.
    uint64_t localEvaluations=0, pcmSseEvaluations=0, activeSseEvaluations=0, pwmSseEvaluations=0;
    // Local FFT scoring calls, including frozen region ranking. Source-analysis
    // construction and complete diagnostic/admission scans are not trials.
    uint64_t noiseEvaluations=0, synthesizedSamples=0;
    int rejectedSize=0, rejectedNative=0, rejectedStability=0, rejectedLevel=0,
        rejectedSpectrum=0, rejectedQuality=0, rejectedFullBand=0, rejectedOldNoise=0,
        rejectedComplete=0;
    ProfileQualityReport noiseSelection, sseSelection;
};

// Return the admitted noise-ranked winner. Active-SSE selection uses the SAME
// shared candidate pool (including a noise-selected first-pulse finalist),
// then forms its own bundles admitted independently against the SAME completed
// baseline. Its bundles never enter the noise winner's pool. This is a paired
// ranking ablation, not a wholly noise-free encoder. Both rankings retain the
// PCM-SSE finalist and incumbent. The new score ranks proposals locally; it
// does not add a complete-output diagnostic floor to the existing admission.
// Raw outputs are the best GENERATED changed complete bundles before admission
// (new diagnostic for noise, active-path SSE for control), including bundles
// worse than the baseline. Only a missing proposal returns the original stream.
// All outputs have the original packet byte count.
// Only ordinary main pulse pairs can change; decoder and all other fields stay
// identical. The total search includes both shared shortlist/ranking branches.
Stream refineLocalNoise(const Stream& completed,const Pcm& reference,LocalNoiseReport& report,
    Stream* rawProposal=nullptr,Stream* sseProposal=nullptr,Stream* sseControl=nullptr);
}
