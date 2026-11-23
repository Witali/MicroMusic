// Direct contracts for the bounded post-incumbent quality phase.
#include "LpxProfileQuality.h"
#include "LpxAdaptiveController.h"
#include "LpxBitrateProfiles.h"
#include "LpxEncoder.h"
#include "LpxFullBand.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <utility>

namespace {
constexpr double pi = 3.14159265358979323846;
int cases = 0;
void require(bool condition, const char* what) {
    if (!condition) { std::fprintf(stderr, "FAIL: %s\n", what); std::exit(1); }
}
lpx::Pcm signal(int n, int rate, double amplitude) {
    lpx::Pcm pcm(n);
    for (int i = 0; i < n; ++i) {
        const double t = double(i) / rate;
        // Exercise the actual Nyquist range, including energy above 4 kHz
        // at the higher supported rates. There is no reference retagging.
        const double envelope = .65 + .25 * std::sin(2 * pi * 7 * t);
        const double value = envelope * (std::sin(2 * pi * 213 * t)
            + .35 * std::sin(2 * pi * 1278 * t)
            + .2 * std::sin(2 * pi * (.43 * rate) * t));
        pcm[i] = int16_t(std::nearbyint(amplitude * value));
    }
    return pcm;
}
bool completeGate(const lpx::Measurement& next, const lpx::Measurement& baseline) {
    if (next.clipped > baseline.clipped) return false;
    for (int path = 0; path < 2; ++path) {
        if (next.diagnostic[path].within < baseline.diagnostic[path].within
            || next.diagnostic[path].collapsed > baseline.diagnostic[path].collapsed) return false;
        if (std::isfinite(baseline.quality.stoi[path])
            && (!std::isfinite(next.quality.stoi[path])
                || next.quality.stoi[path] < baseline.quality.stoi[path] - 1e-12)) return false;
    }
    return true;
}
bool spectralGate(const lpx::FullBandMeasurement& next, const lpx::FullBandMeasurement& baseline) {
    if (!next.valid || !baseline.valid || next.bands != baseline.bands) return false;
    for (int path = 0; path < 2; ++path)
        for (const auto& pair : {std::make_pair(next.totalError[path], baseline.totalError[path]),
                std::make_pair(next.balancedError[path], baseline.balancedError[path]),
                std::make_pair(next.balancedTemporalError[path], baseline.balancedTemporalError[path])})
            if (!std::isfinite(pair.first) || pair.first > pair.second + 1e-12) return false;
    return true;
}
int check(const lpx::Stream& incumbent, const lpx::Pcm& reference,
          int cap, bool finalBudget, bool speech = true, bool threeK = false) {
    const auto frozen = lpx::packV9(incumbent);
    const auto beforePcm = lpx::render(incumbent);
    lpx::QualityContext quality(reference, speech, incumbent.rate);
    lpx::FullBandContext spectrum(reference, incumbent.rate);
    const auto before = quality.measure(beforePcm);
    lpx::ProfileQualityReport report;
    const auto selected = lpx::refineProfileQuality(incumbent, reference,
        cap, finalBudget, report, threeK, speech);
    require(!report.error, "valid phase failed");
    require(lpx::packV9(incumbent) == frozen, "incumbent was mutated");
    require(selected.samples == incumbent.samples && selected.rate == incumbent.rate
        && selected.profile == incumbent.profile, "declared stream changed");
    const int bytes = finalBudget ? int(lpx::packV9(selected).size()) : lpx::compactBytes(selected);
    require(bytes <= cap, "complete stream exceeded the declared cap");
    const auto afterPcm = lpx::render(selected);
    const auto after = quality.measure(afterPcm);
    require(completeGate(after, before), "protected complete quality floor failed");
    require(spectralGate(spectrum.measure(afterPcm), spectrum.measure(beforePcm)),
        "full-frequency PCM/PWM floor failed");
    require(std::isfinite(report.finalObjective) && report.finalObjective <= report.initialObjective + 1e-12,
        "frozen-incumbent-relative objective regressed");
    require(lpx::verifyStream(selected, afterPcm), "native decoder differs");
    require(report.bandwidthCandidates <= 2 && report.localEvaluations <= 246000
        && report.fullEvaluations <= 4, "bounded proposal work exceeded");
    if (!speech) require(!std::isfinite(after.quality.stoi[0])
        && !std::isfinite(after.quality.stoi[1]), "non-speech enabled STOI");
    const int admitted = report.finalObjective < report.initialObjective - 1e-12 ? report.accepted : 0;
    for (int badCap : {0, -1, (finalBudget ? int(frozen.size())
                                          : lpx::compactBytes(incumbent)) - 1}) {
        const auto rejected = lpx::refineProfileQuality(incumbent, reference,
            badCap, finalBudget, report, threeK, speech);
        require(report.error == -6 && !rejected.samples, "invalid cap was not rejected");
        require(lpx::packV9(incumbent) == frozen, "rejected phase mutated incumbent");
    }
    ++cases;
    return admitted;
}
std::vector<uint8_t> simpleEncode(const lpx::Pcm& reference, int profile, int rate) {
    std::memcpy(enc_input(), reference.data(), reference.size() * sizeof(int16_t));
    require(enc_begin(reference.size(), profile, rate) > 0, "simple begin failed");
    int progress;
    do { progress = enc_step(); require(progress >= 0, "simple step failed"); } while (progress < 100);
    const int bytes = enc_finish();
    require(bytes > 0, "simple finish failed");
    return std::vector<uint8_t>(enc_output(), enc_output() + bytes);
}
}
int main() {
    constexpr int capacity = 6401;
    require(enc_set_backend(0) == 0 && enc_reserve(capacity), "CPU workspace failed");
    for (int rate : {8000, 12000, 16000}) for (int profile : {4, 6}) {
        for (int n : {21, 321, 3201}) {
            const auto reference = signal(n, rate, 5000);
            const auto incumbent = lpx::fitSeed(reference, profile, rate, 13926, true);
            require(incumbent.samples == n, "seed failed");
            check(incumbent, reference, lpx::compactBytes(incumbent), false);
            check(incumbent, reference, lpx::packV9(incumbent).size(), true);
        }
        for (double amplitude : {0., 1.}) {
            const auto reference = signal(641, rate, amplitude);
            const auto incumbent = lpx::fitSeed(reference, profile, rate, 13926, true);
            check(incumbent, reference, lpx::compactBytes(incumbent), false);
            check(incumbent, reference, lpx::packV9(incumbent).size(), true, false);
        }
    }
    const auto reference = signal(capacity, 8000, 4500);
    const int cap = capacity * 3 / 64;
    lpx::BitrateReport bitrate;
    const auto threeK = lpx::encodeThreeK(reference, cap, bitrate);
    require(!bitrate.error && threeK.samples == capacity, "strict 3k incumbent failed");
    check(threeK, reference, cap, true, true, true);

    // Long enough that the speech evaluator would produce a finite STOI;
    // this distinguishes speech=false from the short-tail NaN convention.
    const auto nonSpeech = lpx::fitSeed(reference, 6, 8000, 13926, true);
    require(std::isfinite(lpx::QualityContext(reference).measure(lpx::render(nonSpeech)).quality.stoi[0]),
        "active non-speech fixture is too short to distinguish STOI semantics");
    check(nonSpeech, reference, lpx::compactBytes(nonSpeech), false, false);

    lpx::ProfileQualityReport invalid;
    auto invalidRate = nonSpeech; invalidRate.rate = 11025;
    require(!lpx::refineProfileQuality(invalidRate, reference, 100000, false, invalid).samples
        && invalid.error == -1, "unsupported rate was not rejected");
    require(!lpx::refineProfileQuality(threeK, reference, cap, false, invalid, true).samples
        && invalid.error == -1, "strict 3k accepted internal-v5 accounting");

    // A constructed target is reachable with the existing P6 syntax. Its
    // incumbent has lost the first pulse pair, so unchanged fallback alone
    // cannot satisfy this assertion. No corpus output selects this fixture.
    lpx::Stream damaged; damaged.samples = 641; damaged.profile = 6; damaged.pre = 0;
    lpx::Spectrum fixedSpectrum;
    for (int j = 0; j < 10; ++j) fixedSpectrum[j] = 3 + 5 * j;
    damaged.spectra.assign(3, fixedSpectrum);
    // This scale keeps the attainable spectrum above PWM quantization while
    // remaining unclipped; a quieter target can legitimately test rollback.
    damaged.parameters.assign(6, lpx::Parameters{{24, 18, 0}});
    damaged.pulses.assign(48, lpx::Pulse{{0, 0}});
    damaged.extras.assign(24, lpx::Pulse{{-1, 0}});
    auto attainable = damaged;
    attainable.pulses[0] = lpx::Pulse{{9, 7}};
    attainable.pulses[1] = lpx::Pulse{{9, 7}};
    const auto attainablePcm = lpx::render(attainable);
    require(check(damaged, attainablePcm, lpx::compactBytes(damaged), false) > 0,
        "constructed target admitted no actual improvement");

    // A prospective .99 seed and the whole phase must not affect the .97
    // default seed or the original stepped public encoder on their next use.
    const auto resetReference = signal(641, 16000, 5000);
    const auto seedBefore = lpx::packV9(lpx::fitSeed(resetReference, 6, 16000, 13926, true));
    const auto simpleBefore = simpleEncode(resetReference, 6, 16000);
    const auto alternate = lpx::fitSeed(resetReference, 6, 16000, 13926, true, .99);
    check(alternate, resetReference, lpx::compactBytes(alternate), false, false);
    require(lpx::packV9(lpx::fitSeed(resetReference, 6, 16000, 13926, true)) == seedBefore,
        "prospective bandwidth leaked into the next default seed");
    require(simpleEncode(resetReference, 6, 16000) == simpleBefore,
        "prospective bandwidth leaked into enc_begin");

    // A seed backend/workspace failure is reported, not silently replaced
    // with a partially searched result. reserve(0) leaves the prior allocation
    // intact while invalidating its declared capacity, so this copy is safe.
    require(!enc_reserve(0), "invalid reserve succeeded");
    lpx::ProfileQualityReport failure;
    const auto rejected = lpx::refineProfileQuality(alternate, resetReference,
        lpx::compactBytes(alternate), false, failure);
    require(failure.error == -7 && !rejected.samples, "seed failure was hidden");
    require(enc_reserve(capacity), "workspace restore failed");
    std::printf("PASS: %d profile-quality native-rate, full-band, cap, tail, quiet, silence, strict-3k, non-speech and bandwidth-reset contracts.\n", cases);
}
