// Bounded 3 kbit/s P4 search, sharing analysis/synthesis with the host encoder.
// Spectral holding and clipping-aware closed-loop excitation follow the
// accepted encode_low_bitrate_speech.py approach. Selection uses the shared
// whole-output PCM/PWM quality guards, rather than a spectral proxy alone.
#include "LpxBitrateProfiles.h"
#include "LpxAdaptiveController.h"
#include "LpxSeed.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <queue>
#include <tuple>

namespace lpx {
namespace {
const int16_t steps[] = {
#include "scale_table.inc"
};
constexpr uint64_t infiniteLoss = std::numeric_limits<uint64_t>::max();

int riceBits(int value, int k, int width) {
    return value >> k >= 8 ? 8 + width : (value >> k) + 1 + k;
}
int spectrumCost(const Spectrum& current, const Spectrum* previous) {
    if (previous && current == *previous) return 1;
    int gaps = 0, deltas = previous ? 0 : 100000;
    for (int i = 0; i < 10; ++i) {
        gaps += riceBits(current[i] - (i ? current[i - 1] + 1 : 0), 1, 5);
        if (previous) {
            int difference = current[i] - (*previous)[i];
            deltas += riceBits(difference >= 0 ? difference * 2 : -difference * 2 - 1, 0, 6);
        }
    }
    return 2 + std::min(gaps, deltas);
}
int fixedBits(const Stream& s, bool zeroGain = false) {
    // This conservative bound permits every selected gain, including nonzero
    // lag fields. Unlike v5 it counts only packets preceding the actual EOF.
    return ((s.samples + 159) / 160) * (zeroGain ? 8 : 15) + ((s.samples + 39) / 40) * 10;
}
int proposedBytes(const Stream& s, bool zeroGain = false) {
    return (s.samples > 64000 ? 17 : 13) + (spectralBits(s) + fixedBits(s, zeroGain) + 7) / 8;
}

struct Segment {
    int first = 0, last = 0, previous = -1, next = -1, version = 0;
    bool active = true;
    double weight = 0, sum[10] = {}, square[10] = {};
    Spectrum center;
};
Spectrum center(const Segment& segment) {
    Spectrum result;
    for (int j = 0; j < 10; ++j)
        result[j] = clamp(int(std::nearbyint(segment.sum[j] / segment.weight)), 0, 31);
    for (int j = 1; j < 10; ++j) result[j] = std::max(result[j], result[j - 1] + 1);
    if (result[9] > 31) {
        result[9] = 31;
        for (int j = 8; j >= 0; --j) result[j] = std::min(result[j], result[j + 1] - 1);
    }
    return result;
}
double spectralLoss(const Segment& segment) {
    double result = 0;
    for (int j = 0; j < 10; ++j) {
        double c = segment.center[j];
        result += segment.square[j] - 2 * c * segment.sum[j] + c * c * segment.weight;
    }
    return result;
}
Segment merged(const Segment& a, const Segment& b) {
    Segment result = a;
    result.last = b.last; result.next = b.next; result.weight += b.weight;
    for (int j = 0; j < 10; ++j) {
        result.sum[j] += b.sum[j]; result.square[j] += b.square[j];
    }
    result.center = center(result); return result;
}
struct Merge {
    int left, right, previous, next, lv, rv, pv, nv, saved;
    double delta;
};
struct LaterMerge {
    bool operator()(const Merge& a, const Merge& b) const {
        double ar = a.delta / a.saved, br = b.delta / b.saved;
        return ar != br ? ar > br : a.delta != b.delta ? a.delta > b.delta : a.left > b.left;
    }
};

std::vector<std::vector<Spectrum>> spectralPlans(const Stream& seed, const Pcm& reference, int cap, bool zeroGain = false) {
    const int frames = seed.spectra.size();
    std::vector<std::vector<Spectrum>> result;
    Stream trial = seed;
    // A logarithmically bounded uniform control always reaches a whole-input
    // hold. Only an actually serialized-size-compatible plan is retained.
    for (int cadence = 1;; cadence = std::min(frames, cadence * 2)) {
        for (int i = 0; i < frames; ++i) trial.spectra[i] = seed.spectra[(i / cadence) * cadence];
        if (proposedBytes(trial, zeroGain) <= cap) { result.push_back(trial.spectra); break; }
        if (cadence == frames) break;
    }
    std::vector<Segment> segments(frames);
    for (int i = 0; i < frames; ++i) {
        auto& item = segments[i]; item.first = i; item.last = i + 1;
        item.previous = i - 1; item.next = i + 1 < frames ? i + 1 : -1;
        double energy = 0; int stop = std::min(seed.samples, (i + 1) * 320);
        for (int at = i * 320; at < stop; ++at) energy += double(reference[at]) * reference[at];
        item.weight = 1 + std::sqrt(energy / std::max(1, stop - i * 320));
        item.center = seed.spectra[i];
        for (int j = 0; j < 10; ++j) {
            item.sum[j] = item.weight * item.center[j];
            item.square[j] = item.sum[j] * item.center[j];
        }
    }
    std::priority_queue<Merge, std::vector<Merge>, LaterMerge> queue;
    auto version = [&](int i) { return i < 0 ? -1 : segments[i].version; };
    auto enqueue = [&](int index) {
        if (index < 0 || !segments[index].active || segments[index].next < 0) return;
        const auto& a = segments[index]; const auto& b = segments[a.next];
        auto joined = merged(a, b); int p = a.previous, n = b.next;
        const Spectrum* previous = p < 0 ? nullptr : &segments[p].center;
        int before = spectrumCost(a.center, previous) + spectrumCost(b.center, &a.center);
        int after = spectrumCost(joined.center, previous) + 1;
        if (n >= 0) { before += spectrumCost(segments[n].center, &b.center); after += spectrumCost(segments[n].center, &joined.center); }
        if (before > after) queue.push({index, a.next, p, n, a.version, b.version,
            version(p), version(n), before - after, spectralLoss(joined) - spectralLoss(a) - spectralLoss(b)});
    };
    for (int i = 0; i < frames; ++i) enqueue(i);
    int bits = spectralBits(seed);
    auto fits = [&]() { return (seed.samples > 64000 ? 17 : 13) + (bits + fixedBits(seed, zeroGain) + 7) / 8 <= cap; };
    while (!fits() && !queue.empty()) {
        Merge candidate = queue.top(); queue.pop();
        auto& a = segments[candidate.left]; auto& b = segments[candidate.right];
        if (!a.active || !b.active || a.next != candidate.right || a.previous != candidate.previous
            || b.next != candidate.next || version(candidate.left) != candidate.lv
            || version(candidate.right) != candidate.rv || version(candidate.previous) != candidate.pv
            || version(candidate.next) != candidate.nv) continue;
        a = merged(a, b); ++a.version; b.active = false; ++b.version;
        if (a.next >= 0) segments[a.next].previous = candidate.left;
        bits -= candidate.saved;
        int previous = a.previous;
        if (previous >= 0) enqueue(segments[previous].previous);
        enqueue(previous); enqueue(candidate.left); enqueue(a.next);
    }
    if (fits()) {
        for (int i = 0; i >= 0; i = segments[i].next)
            for (int j = segments[i].first; j < segments[i].last; ++j) trial.spectra[j] = segments[i].center;
        // The local bit deltas are an allocation acceleration, not authority.
        if (proposedBytes(trial, zeroGain) <= cap && (result.empty() || trial.spectra != result[0]))
            result.push_back(trial.spectra);
    }
    return result;
}

uint64_t trialGroup(const Stream& s, const std::vector<Coefficients>& co, const Pcm& reference,
                    const SynthesisState& initial, SynthesisState& state, int start,
                    int scale, int lag, int gain, int position, int amplitude, bool guard, uint64_t bound) {
    state = initial; uint64_t loss = 0; const int stop = std::min(s.samples, start + 20);
    for (int at = start; at < stop; ++at) {
        int q = clamp((gain * state.ring[(at - lag) & 255] + 8) >> 4, -32, 31);
        q = clamp(q + (at - start == position ? amplitude : 0), -32, 31); state.ring[at & 255] = q;
        int accumulator = 0;
        for (int k = 0; k < 10; ++k) accumulator += (co[at / 20][k] * state.h[k]) >> 12;
        int predicted = clamp(q * steps[scale * 8] - accumulator);
        for (int k = 9; k; --k) state.h[k] = state.h[k - 1]; state.h[0] = predicted;
        state.dd = clamp(predicted + ((s.pre * state.dd) >> 14));
        state.cc = clamp(state.dd, -16384, 16384);
        int sample = clamp(state.cc * 2, -32768, 32767);
        int64_t difference = int64_t(sample) - reference[at]; loss += uint64_t(difference * difference);
        if (guard && (sample == -32768 || sample == 32767)) loss += uint64_t(1) << 42;
        if (loss >= bound) break;
    }
    return loss;
}
uint64_t fitBlock(Stream& s, const std::vector<Coefficients>& co, const Pcm& reference,
                  const SynthesisState& initial, SynthesisState& result, int start,
                  int scale, int lag, int gain, bool guard, bool save, uint64_t bound, BitrateReport& report) {
    auto state = initial; uint64_t total = 0;
    for (int at = start; at < start + 160 && at < s.samples; at += 20) {
        if (total >= bound) return total;
        uint64_t best = infiniteLoss; int bestPosition = 0, bestAmplitude = -8;
        SynthesisState trial;
        for (int code = 0; code < 16; ++code) for (int sign = 0; sign < 2; ++sign) {
            int position = code + ((code + 2) >> 2), amplitude = sign ? 8 : -8;
            uint64_t error = trialGroup(s, co, reference, state, trial, at, scale, lag, gain,
                position, amplitude, guard, std::min(best, bound - total)); ++report.pulseTrials;
            if (error < best) { best = error; bestPosition = position; bestAmplitude = amplitude; }
        }
        SynthesisState next;
        total += trialGroup(s, co, reference, state, next, at, scale, lag, gain,
            bestPosition, bestAmplitude, guard, infiniteLoss); state = next;
        if (save) s.pulses[at / 20] = Pulse{{bestPosition, bestAmplitude}};
    }
    result = state; return total;
}
std::vector<int> sourcePeriods(const Pcm& reference) {
    std::vector<int> periods;
    for (int start = 0; start + 640 <= int(reference.size()); start += 160) {
        double frame[640], rms;
        for (int j = 0; j < 640; ++j) frame[j] = reference[start + j];
        double period = estimatePeriod(frame, 640, rms);
        periods.push_back(std::isfinite(period) ? int(std::nearbyint(period)) : 0);
    }
    return periods;
}
void fitExcitation(Stream& s, const Pcm& reference, const std::vector<int>& periods, bool expanded, BitrateReport& report, bool zeroGain = false) {
    const auto co = coefficientTrace(s);
    const int n = s.samples;
    std::vector<double> emphasized(n), residual(n);
    for (int at = 0; at < n; ++at) {
        emphasized[at] = reference[at] / 2. - (at ? s.pre * (reference[at - 1] / 2.) / 16384 : 0);
        residual[at] = emphasized[at];
        for (int k = 0; k < 10 && at > k; ++k) residual[at] += co[at / 20][k] * emphasized[at - k - 1] / 4096;
    }
    s.parameters.assign(s.spectra.size() * 2, Parameters{{0, 18, 0}});
    s.pulses.assign(s.spectra.size() * 16, Pulse{{0, -8}});
    s.extras.assign(s.spectra.size() * 8, Pulse{{-1, 0}});
    SynthesisState prefix;
    for (int start = 0; start < n; start += 160) {
        int stop = std::min(n, start + 160), bi = start / 160;
        double power = 0, scores[128];
        for (int at = start; at < stop; ++at) power += residual[at] * residual[at];
        double desired = std::max(1., std::sqrt(power / (stop - start) * 20) / 7.5);
        int middle = clamp(int(std::nearbyint((128 + 16 * std::log2(desired / 16.384)) / 8)), 1, 31);
        for (int lag = 18; lag <= 145; ++lag) {
            double dot = 0, energy = 0;
            for (int at = start; at < stop; ++at) {
                double old = at >= lag ? residual[at - lag] : 0;
                dot += old * residual[at]; energy += old * old;
            }
            scores[lag - 18] = std::max(0., dot) * std::max(0., dot) / (energy + 1);
        }
        std::vector<int> lags{int(std::max_element(scores, scores + 128) - scores) + 18};
        auto appendLag = [&](int lag) { if (lag >= 18 && lag <= 145 && std::find(lags.begin(), lags.end(), lag) == lags.end()) lags.push_back(lag); };
        if (expanded && !zeroGain) {
            if (!periods.empty()) {
                int period = periods[clamp(bi - 2, 0, int(periods.size()) - 1)];
                appendLag(period); appendLag(period - 1); appendLag(period + 1);
            }
            for (int repeat = 0; repeat < 2; ++repeat) {
                for (int i = 0; i < 128; ++i) for (int lag : lags) if (std::abs(i + 18 - lag) <= 2) scores[i] = -1;
                appendLag(int(std::max_element(scores, scores + 128) - scores) + 18);
            }
        }
        std::vector<int> scales;
        for (int scale = std::max(0, middle - 2); scale <= std::min(31, middle + 2); ++scale) scales.push_back(scale);
        for (int scale : {0, 1}) if (std::find(scales.begin(), scales.end(), scale) == scales.end()) scales.push_back(scale);
        uint64_t best = infiniteLoss; Parameters selected{{0, lags[0], 0}}; SynthesisState trial;
        for (int scale : scales) for (int li = 0; li < int(lags.size()); ++li)
            for (int gain = 0; gain <= (zeroGain ? 0 : 14); gain += 2) {
                if ((!expanded && gain != 0 && gain != 6 && gain != 10 && gain != 14) || (li && !gain)) continue;
                uint64_t error = fitBlock(s, co, reference, prefix, trial, start, scale, lags[li], gain,
                    expanded, false, best, report); ++report.parameterTrials;
                if (error < best) { best = error; selected = Parameters{{scale, lags[li], gain}}; }
            }
        fitBlock(s, co, reference, prefix, trial, start, selected[0], selected[1], selected[2], expanded, true, infiniteLoss, report);
        prefix = trial; s.parameters[bi] = selected;
    }
}
}

Stream encodeThreeK(const Pcm& reference, int maxBytes, BitrateReport& report) {
    report = BitrateReport{};
    if (reference.empty() || reference.size() > lpxSeedCapacity() || maxBytes < 13) {
        report.error = -1; return Stream{};
    }
    const auto periods = sourcePeriods(reference);
    QualityContext context(reference); Measurement baseline, selectedMeasurement;
    Stream selected; size_t selectedBytes = 0;
    auto add = [&](const Stream& candidate) {
        auto bytes = packV9(candidate);
        if (int64_t(bytes.size()) > maxBytes) return;
        auto pcm = render(candidate);
        if (!verifyStream(candidate, pcm)) { report.error = -3; return; }
        auto measurement = context.measure(pcm); int ordinal = report.candidates++;
        if (ordinal == 0) baseline = measurement;
        bool admissible = noRegression(measurement.quality, baseline.quality)
            && measurement.clipped <= baseline.clipped
            && measurement.diagnostic[0].within >= baseline.diagnostic[0].within
            && measurement.diagnostic[1].within >= baseline.diagnostic[1].within;
        if (admissible && (!selected.samples || measurement.score < selectedMeasurement.score
            || (measurement.score == selectedMeasurement.score && bytes.size() < selectedBytes))) {
            selected = candidate; selectedMeasurement = measurement; selectedBytes = bytes.size(); report.selected = ordinal;
        }
    };
    for (int pre : {13926, 11469, 8192}) {
        Stream seed = fitSeed(reference, 4, 8000, pre, true);
        // The complete existing seed is a legitimate candidate when V9's exact
        // zero-gain/tail omissions already place it under the requested cap.
        if (int64_t(packV9(seed).size()) <= maxBytes) add(seed);
        if (report.error) return Stream{};
        // Neither waveform floor can improve beyond an exact PCM/PWM match.
        // In particular, do not exhaustively refit every silent innovation.
        if (selected.samples && !selectedMeasurement.quality.error[0] && !selectedMeasurement.quality.error[1]) return selected;
        auto plans = spectralPlans(seed, reference, maxBytes);
        for (const auto& spectra : plans) {
            Stream candidate = seed; candidate.spectra = spectra;
            if (!report.candidates) { fitExcitation(candidate, reference, periods, false, report); add(candidate); }
            fitExcitation(candidate, reference, periods, true, report); add(candidate);
            if (report.error) return Stream{};
        }
    }
    if (!report.candidates && !report.error) {
        // A short stream may fit only after actual zero-gain lag omission.
        // Try this explicit bounded alternative before returning search no-fit;
        // it is not used to displace any already feasible ordinary candidate.
        for (int pre : {13926, 11469, 8192}) {
            Stream seed = fitSeed(reference, 4, 8000, pre, true);
            auto plans = spectralPlans(seed, reference, maxBytes, true);
            for (const auto& spectra : plans) {
                Stream candidate = seed; candidate.spectra = spectra;
                fitExcitation(candidate, reference, periods, true, report, true); add(candidate);
                if (report.error) return Stream{};
            }
        }
    }
    if (!selected.samples) report.error = -6;
    return selected;
}
}
