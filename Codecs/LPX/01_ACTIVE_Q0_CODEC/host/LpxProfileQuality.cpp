// Encoder-only proposals. No decoder state, instruction or wire format added.
#include "LpxProfileQuality.h"
#include "LpxAdaptiveController.h"
#include "LpxBitrateProfiles.h"
#include "LpxFullBand.h"
#include "LpxPulseLookahead.h"
#include "LpxRefinement.h"
#include "LpxLpcRefine.h"
#include "LpxPitchGuard.h"
#include "LpxSpectralPulses.h"
#include <cmath>
#include <utility>
#include <memory>

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
// One owner for complete-output admission. Each search phase supplies an
// immutable incumbent and uses the same metric equations and tie ordering.
class QualitySelection {
    int cap;
    bool finalV9Budget;
    ProfileQualityReport& report;
    FullBandContext spectrum;
    Pcm initialPcm;
    FullBandMeasurement baselineSpectrum;
    double selectedObjective;
    int selectedBytes;
    std::vector<std::vector<uint8_t>> seen;
    std::unique_ptr<PitchGuardContext> pitchGuard;
    int bytes(const Stream& stream) const {
        return finalV9Budget ? int(packV9(stream).size()) : compactBytes(stream);
    }
public:
    QualityContext quality;
    Measurement baseline;
    Stream selected;
    QualitySelection(const Stream& incumbent, const Pcm& reference, int cap,
        bool finalV9Budget, ProfileQualityReport& report, bool speech, bool protectOctaves=false)
        : cap(cap), finalV9Budget(finalV9Budget), report(report),
          spectrum(reference,incumbent.rate), initialPcm(render(incumbent)),
          quality(reference,speech,incumbent.rate), selected(incumbent) {
        baseline=quality.measure(initialPcm);
        baselineSpectrum=spectrum.measure(initialPcm);
        selectedObjective=objective(baseline,baselineSpectrum,baseline,baselineSpectrum);
        selectedBytes=bytes(incumbent);
        seen.push_back(packV9(incumbent));
        if(!verifyStream(incumbent,initialPcm)) { report.error=-3;return; }
        if(protectOctaves)pitchGuard.reset(new PitchGuardContext(reference,initialPcm,incumbent.rate));
        report.initialObjective=report.finalObjective=selectedObjective;
    }
    bool add(const Stream& candidate,double* safeScore=nullptr) {
        if(safeScore)*safeScore=std::numeric_limits<double>::infinity();
        if(!candidate.samples || bytes(candidate)>cap)return false;
        auto packed=packV9(candidate);
        for(const auto& old:seen)if(packed==old)return false;
        seen.push_back(std::move(packed));++report.candidates;
        const auto pcm=render(candidate);
        if(!verifyStream(candidate,pcm)) { report.error=-3;return false; }
        const auto measured=quality.measure(pcm);
        const auto spectral=spectrum.measure(pcm);
        if(!safety(measured,spectral,baseline,baselineSpectrum))return false;
        const double score=objective(measured,spectral,baseline,baselineSpectrum);
        const bool safeImprovement=score<report.initialObjective-1e-12;
        const int count=bytes(candidate);
        if(pitchGuard&&(safeImprovement||(score==selectedObjective&&count<selectedBytes))
            &&!pitchGuard->accepts(pcm)) {++report.octaveRejected;return false;}
        if(safeScore&&safeImprovement)*safeScore=score;
        if(score<selectedObjective-1e-12 || (score==selectedObjective && count<selectedBytes)) {
            selected=candidate;selectedBytes=count;selectedObjective=score;
            report.finalObjective=score;++report.accepted;
        }
        return safeImprovement;
    }
};
}
Stream selectQualityProposals(const Stream& incumbent,const Pcm& reference,
    std::initializer_list<const Stream*> proposals,ProfileQualityReport& report,bool speech,int completeV9Budget) {
    report=ProfileQualityReport{};
    QualitySelection selection(incumbent,reference,completeV9Budget?completeV9Budget:std::numeric_limits<int>::max(),true,
        report,speech,LPX_ENCODER_JOINT_REFINEMENT!=0);
    if(report.error)return Stream{};
    for(const auto* candidate:proposals) {
        if(!candidate||candidate->samples!=incumbent.samples||candidate->rate!=incumbent.rate
            ||candidate->profile!=incumbent.profile)continue;
        selection.add(*candidate);
        if(report.error)return Stream{};
    }
    return report.finalObjective<report.initialObjective-1e-12?selection.selected:incumbent;
}
bool profileQualityAdmission(const Pcm& reference,const Pcm& incumbent,const Pcm& candidate,int rate,bool speech,bool strictlyBetter) {
    if(reference.size()!=incumbent.size() || reference.size()!=candidate.size())return false;
    QualityContext quality(reference,speech,rate);FullBandContext spectrum(reference,rate);
    const auto baseline=quality.measure(incumbent),next=quality.measure(candidate);
    const auto spectralFloor=spectrum.measure(incumbent),proposal=spectrum.measure(candidate);
    const double score=objective(next,proposal,baseline,spectralFloor),floor=objective(baseline,spectralFloor,baseline,spectralFloor);
    const bool admitted=safety(next,proposal,baseline,spectralFloor)
        && (strictlyBetter?score<floor-1e-12:score<=floor+1e-12);
#if LPX_ENCODER_JOINT_REFINEMENT
    // Window-local guards cannot see every boundary-crossing pitch window.
    // The assembled continuous output gets the same source-frozen check.
    if(admitted) {
        const PitchGuardContext pitch(reference,incumbent,rate);
        return pitch.accepts(candidate);
    }
#endif
    return admitted;
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
    QualitySelection selection(incumbent,reference,cap,finalV9Budget,report,speech);
    if(report.error)return Stream{};
    auto& selected=selection.selected;
    const auto& baseline=selection.baseline;
    auto add=[&](const Stream& candidate) { selection.add(candidate); };
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
        const auto pairs = refinePulseLookahead(selected, selection.quality, cap, finalV9Budget);
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
Stream refineJointQuality(const Stream& incumbent, const Pcm& reference,
    int cap, bool finalV9Budget, JointQualityReport& report, bool threeK, bool speech) {
    report=JointQualityReport{};
    if(incumbent.samples!=int(reference.size()) || reference.empty()
        || (incumbent.profile!=4 && incumbent.profile!=6)
        || (incumbent.rate!=8000 && incumbent.rate!=12000 && incumbent.rate!=16000)
        || (threeK && (!finalV9Budget || incumbent.profile!=4 || incumbent.rate!=8000))) {
        report.selection.error=-1;return Stream{};
    }
    if((finalV9Budget ? int64_t(packV9(incumbent).size()) : compactBytes(incumbent))>cap) {
        report.selection.error=-6;return Stream{};
    }
    QualitySelection selection(incumbent,reference,cap,finalV9Budget,report.selection,speech,true);
    if(report.selection.error)return Stream{};
    if(!selection.baseline.quality.error[0] && !selection.baseline.quality.error[1])return incumbent;
    auto header=[&]() {
        if(incumbent.continuation)return; // A continuous file has one header.
        // Header coefficients cost no additional payload bytes. This existing
        // operator supplies proposals; the common full-band gate still decides.
        auto proposals=refineHeader(selection.selected,selection.quality);
        report.headerLocalEvaluations+=proposals.localEvaluations;
        report.headerFullEvaluations+=proposals.fullEvaluations;
        // A tiny numerical gain has not justified activating an extra
        // per-sample brightness multiply. Keep the V3 disabled-filter state;
        // the pre-emphasis candidates are still evaluated completely.
        if(!incumbent.bright) {
            proposals.selected.bright=proposals.raw.bright=0;
            for(auto& candidate:proposals.alternatives)candidate.bright=0;
        }
        selection.add(proposals.selected);selection.add(proposals.raw);
        for(const auto& candidate:proposals.alternatives)selection.add(candidate);
    };
    if(threeK) {
        header();
        if(report.selection.error)return Stream{};
    }
#if LPX_ENCODER_LPC_RUNS
    const Stream lpcAnchor=selection.selected;
    const auto lpc=proposeLpcRuns(lpcAnchor,reference,cap,finalV9Budget);
    report.lpcRuns=lpc.runs;report.lpcProposals=lpc.proposals.size();
    report.lpcSpectralEvaluations=lpc.spectralEvaluations;
    report.lpcPulseEvaluations=lpc.pulseEvaluations;
    report.lpcSynthesizedSamples=lpc.synthesizedSamples;
    std::vector<double> safeScores(lpc.proposals.size(),std::numeric_limits<double>::infinity());
    for(size_t i=0;i<lpc.proposals.size();++i)selection.add(lpc.proposals[i],&safeScores[i]);
    const auto bundles=composeLpcRuns(lpcAnchor,lpc.proposals,safeScores,cap,finalV9Budget);
    report.lpcBundles=bundles.size();
    for(const auto& bundle:bundles)selection.add(bundle);
    if(report.selection.error)return Stream{};
#endif
    if(threeK) {
        header();
        if(report.selection.error)return Stream{};
    }
    return selection.selected;
}
}
