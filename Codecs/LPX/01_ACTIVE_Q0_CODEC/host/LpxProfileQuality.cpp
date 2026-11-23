// Encoder-only proposals. No decoder state, instruction or wire format added.
#include "LpxProfileQuality.h"
#include "LpxAdaptiveController.h"
#include "LpxBitrateProfiles.h"
#include "LpxFullBand.h"
#include "LpxPulseLookahead.h"
#include "LpxSpectralPulses.h"
#include <cmath>
#include <utility>

namespace lpx {
namespace {
// Relative errors refer to the frozen complete incumbent. Zero errors are
// exact floors; no output-dependent gain, delay or reference is fitted.
double relativeError(double value,double baseline) {
    if(!std::isfinite(value) || value<0)return std::numeric_limits<double>::infinity();
    if(baseline==0)return value==0?0:std::numeric_limits<double>::infinity();
    return value/baseline;
}
double objective(const Measurement& m,const FullBandMeasurement& spectrum,
                 const Measurement& floor,const FullBandMeasurement& spectralFloor) {
    double total=0,weight=0;
    for(int path=0;path<2;++path) {
        // Spectral and temporal losses each carry twice an ordinary metric's
        // weight. All comparisons use the same frozen incumbent denominators.
        total+=2*relativeError(spectrum.balancedError[path],spectralFloor.balancedError[path]);
        total+=2*relativeError(spectrum.balancedTemporalError[path],spectralFloor.balancedTemporalError[path]);
        total+=relativeError(m.voice[path],floor.voice[path]);
        total+=relativeError(m.noise[path],floor.noise[path]);
        total+=relativeError(double(m.quality.error[path]),double(floor.quality.error[path]));
        weight+=7;
        if(std::isfinite(floor.quality.stoi[path])) {
            total+=relativeError(std::max(0.,1-m.quality.stoi[path]),std::max(0.,1-floor.quality.stoi[path]));
            ++weight;
        }
        if(std::isfinite(floor.diagnostic[path].period)) {
            total+=relativeError(m.diagnostic[path].period,floor.diagnostic[path].period);
            ++weight;
        }
        if(std::isfinite(floor.diagnostic[path].shape)) {
            total+=relativeError(m.diagnostic[path].shape,floor.diagnostic[path].shape);
            ++weight;
        }
    }
    return total/weight;
}
bool safety(const Measurement& m,const FullBandMeasurement& spectrum,
            const Measurement& floor,const FullBandMeasurement& spectralFloor) {
    if(!spectrum.valid || m.clipped>floor.clipped)return false;
    for(int path=0;path<2;++path) {
        if(std::isfinite(floor.quality.stoi[path]) && (!std::isfinite(m.quality.stoi[path])
            || m.quality.stoi[path]<floor.quality.stoi[path]-1e-12))return false;
        if(m.diagnostic[path].within<floor.diagnostic[path].within
            || m.diagnostic[path].collapsed>floor.diagnostic[path].collapsed)return false;
        if(spectrum.totalError[path]>spectralFloor.totalError[path]+1e-12
            || spectrum.balancedError[path]>spectralFloor.balancedError[path]+1e-12
            || spectrum.balancedTemporalError[path]>spectralFloor.balancedTemporalError[path]+1e-12)return false;
    }
    return true;
}
}
bool profileQualityAdmission(const Pcm& reference,const Pcm& incumbent,const Pcm& candidate,int rate,bool speech) {
    if(reference.size()!=incumbent.size() || reference.size()!=candidate.size())return false;
    QualityContext quality(reference,speech,rate);FullBandContext spectrum(reference,rate);
    const auto baseline=quality.measure(incumbent),next=quality.measure(candidate);
    const auto spectralFloor=spectrum.measure(incumbent),proposal=spectrum.measure(candidate);
    return safety(next,proposal,baseline,spectralFloor)
        && objective(next,proposal,baseline,spectralFloor)<=objective(baseline,spectralFloor,baseline,spectralFloor)+1e-12;
}
Stream refineProfileQuality(const Stream& incumbent, const Pcm& reference,
    int cap, bool finalV9Budget, ProfileQualityReport& report, bool threeK, bool speech) {
    report = ProfileQualityReport{};
    if (incumbent.samples != int(reference.size()) || reference.empty()
        || (incumbent.profile != 4 && incumbent.profile != 6)
        || (incumbent.rate != 8000 && incumbent.rate != 12000 && incumbent.rate != 16000)
        || (threeK && (!finalV9Budget || incumbent.profile != 4 || incumbent.rate != 8000))) {
        report.error = -1; return Stream{};
    }
    auto bytes = [&](const Stream& s) {
        return finalV9Budget ? int(packV9(s).size()) : compactBytes(s);
    };
    if (bytes(incumbent) > cap) { report.error = -6; return Stream{}; }
    // This context uses the actual sample rate. The old controller remains a
    // protected source of candidates, including at 12/16 kHz.
    QualityContext quality(reference, speech, incumbent.rate);
    FullBandContext spectrum(reference, incumbent.rate);
    const Pcm initialPcm = render(incumbent);
    const auto baseline = quality.measure(initialPcm);
    const auto baselineSpectrum = spectrum.measure(initialPcm);
    if (!verifyStream(incumbent, initialPcm)) { report.error = -3; return Stream{}; }
    Stream selected = incumbent;
    double selectedObjective=objective(baseline,baselineSpectrum,baseline,baselineSpectrum);
    report.initialObjective=report.finalObjective=selectedObjective;
    int selectedBytes = bytes(incumbent);
    std::vector<std::vector<uint8_t>> seen{packV9(incumbent)};
    auto add = [&](const Stream& candidate) {
        if (!candidate.samples || bytes(candidate) > cap) return;
        auto packed = packV9(candidate);
        for (const auto& old : seen) if (packed == old) return;
        seen.push_back(std::move(packed)); ++report.candidates;
        const auto pcm = render(candidate);
        if (!verifyStream(candidate, pcm)) { report.error = -3; return; }
        const auto measured = quality.measure(pcm);
        const auto spectral=spectrum.measure(pcm);
        if(!safety(measured,spectral,baseline,baselineSpectrum))return;
        const double score=objective(measured,spectral,baseline,baselineSpectrum);
        const int count = bytes(candidate);
        if (score < selectedObjective-1e-12
            || (score == selectedObjective && count < selectedBytes)) {
            selected = candidate;
            selectedBytes = count;selectedObjective=score;
            report.finalObjective=score;++report.accepted;
        }
    };
    // Fixed prospective proposals, not corpus-fitted coefficients. All other
    // seed callers retain .97 and the protected incumbent is always available.
    if (baseline.quality.error[0] || baseline.quality.error[1]) {
        for (double bandwidth : {.94, .99}) {
            Stream proposal;
            if (threeK) {
                BitrateReport search;
                proposal = encodeThreeK(reference, cap, search, bandwidth, &incumbent,
                    incumbent.continuation || !incumbent.allowExtras?&incumbent:nullptr);
                if (search.error) { report.error = search.error; return Stream{}; }
            } else {
                proposal = fitSeed(reference, incumbent.profile, incumbent.rate,
                    incumbent.pre, true, bandwidth,
                    incumbent.continuation || !incumbent.allowExtras?&incumbent:nullptr);
                if (!proposal.samples) { report.error = -7; return Stream{}; }
            }
            ++report.bandwidthCandidates;
            add(proposal);
            if (report.error) return Stream{};
            if (!threeK && proposal.bright != incumbent.bright) {
                proposal.bright = incumbent.bright;
                add(proposal);
                if (report.error) return Stream{};
            }
        }
        const auto pairs = refinePulseLookahead(selected, quality, cap, finalV9Budget);
        report.localEvaluations = pairs.localEvaluations;
        report.fullEvaluations = pairs.fullEvaluations;
        add(pairs.selected); add(pairs.raw);
        for (const auto& alternative : pairs.alternatives) add(alternative);
        if (report.error) return Stream{};
#if LPX_ENCODER_SPECTRAL_PULSES
        // Noise can have the right spectrum without the same sample phase.
        // Local magnitude/time ranking supplies complementary proposals; the
        // same complete multi-metric gate and protected minimum still decide.
        const auto spectral=proposeSpectralPulses(selected,reference);
        report.spectralLocalEvaluations=spectral.localEvaluations;
        report.spectralProposals=spectral.proposals.size();
        report.spectralRegions=spectral.regions;
        for(const auto& proposal:spectral.proposals)add(proposal);
        if(report.error)return Stream{};
#endif
    }
    return selected;
}
}
