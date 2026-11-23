// Bounded pairwise excitation search with delayed integer-synthesis scoring.
// Uses the same advance() model as every other host quality operator.
#include "LpxPulseLookahead.h"
#include <algorithm>
#include <tuple>

namespace lpx {
namespace {
constexpr int maxFrames = 24;
constexpr int horizon = 160;

bool completeGate(const Measurement& next, const Measurement& baseline) {
    return next.score <= baseline.score + 1e-12
        && noRegression(next.quality, baseline.quality)
        && next.clipped <= baseline.clipped
        && next.diagnostic[0].within >= baseline.diagnostic[0].within
        && next.diagnostic[1].within >= baseline.diagnostic[1].within;
}

std::vector<int> anchors(const Pcm& reference, const Pcm& pcm) {
    const int frames = (reference.size() + 319) / 320;
    std::vector<int> order(frames);
    std::vector<uint64_t> errors(frames);
    for (int frame = 0; frame < frames; ++frame) {
        order[frame] = frame;
        for (int at = frame * 320; at < std::min(int(reference.size()), frame * 320 + 320); ++at) {
            int64_t difference = int(reference[at]) - int(pcm[at]);
            errors[frame] += uint64_t(difference * difference);
        }
    }
    if (frames <= maxFrames) return order;
    std::sort(order.begin(), order.end(), [&](int a, int b) {
        return errors[a] != errors[b] ? errors[a] > errors[b] : a < b;
    });
    std::vector<int> selected(order.begin(), order.begin() + maxFrames / 2);
    auto append = [&](int frame) {
        if (std::find(selected.begin(), selected.end(), frame) == selected.end()) selected.push_back(frame);
    };
    for (int i = 0; i < maxFrames / 2; ++i) append(i * (frames - 1) / (maxFrames / 2 - 1));
    for (int frame : order) {
        if (selected.size() >= maxFrames) break;
        append(frame);
    }
    std::sort(selected.begin(), selected.end());
    return selected;
}

template<class F> void legalPulses(int profile, F evaluate) {
    for (int position = 0; position < 20; ++position) {
        if (profile == 4 && position % 5 == 2) continue;
        for (int amplitude = -8; amplitude <= (profile == 4 ? 8 : 7); ++amplitude) {
            if (profile == 4 && amplitude != -8 && amplitude != 8) continue;
            // All zero-amplitude positions produce the same state. The exact
            // incumbent is considered separately before this canonical zero.
            if (!amplitude && position) continue;
            evaluate(Pulse{{position, amplitude}});
        }
    }
}

// A monotone walk bounds prefix work to one full input traversal. Chunking
// avoids allocating a gap-sized output vector merely to recover its state.
void walkTo(const Stream& stream, const std::vector<Coefficients>& co,
            int stop, int& cursor, SynthesisState& state) {
    while (cursor < stop) {
        int end = std::min(stop, cursor + 4096);
        advance(stream, co, cursor, end, state);
        cursor = end;
    }
}

struct FirstChoice {
    Pulse pulse;
    SynthesisState after;
    uint64_t prefixLoss = 0, lookaheadLoss = 0;
};
struct Patch {
    int start;
    Pulse first, second;
    uint64_t benefit;
};
}

RefinementResult refinePulseLookahead(const Stream& input,
    const QualityContext& context, int cap, bool finalV9Budget) {
    RefinementResult result;
    result.selected = result.raw = input;
    if ((input.profile != 4 && input.profile != 6) || input.samples < 1
        || size_t(input.samples) != context.reference.size()) return result;
    const auto cost = [&](const Stream& stream) {
        return finalV9Budget ? int(packV9(stream).size()) : compactBytes(stream);
    };
    const int bytes = cost(input);
    if (bytes > cap) return result;
    const auto co = coefficientTrace(input);
    const auto originalPcm = render(input);
    const auto baseline = context.measure(originalPcm);
    if (!baseline.quality.error[0]) return result;

    Stream working = input;
    auto prefix=input.initial;
    int cursor = 0;
    std::vector<Patch> patches;
    for (int frame : anchors(context.reference, originalPcm)) {
        for (int packet = 0; packet < 8; ++packet) {
            const int start = frame * 320 + packet * 40;
            if (start >= input.samples) break;
            walkTo(working, co, start, cursor, prefix);
            const int firstIndex = start / 20;
            const int secondStart = std::min(input.samples, start + 20);
            const int end = std::min(input.samples, start + horizon);
            const auto oldFirst = working.pulses[firstIndex];
            const auto oldSecond = working.pulses[firstIndex + 1];
            auto firstTrial = [&](Pulse pulse) {
                working.pulses[firstIndex] = pulse;
                FirstChoice choice;
                choice.pulse = pulse; choice.after = prefix;
                auto out = advance(working, co, start, secondStart, choice.after);
                choice.prefixLoss = sse(context.reference, out, start);
                auto future = choice.after;
                out = advance(working, co, secondStart, end, future);
                choice.lookaheadLoss = choice.prefixLoss + sse(context.reference, out, secondStart);
                ++result.localEvaluations;
                return choice;
            };
            const auto incumbent = firstTrial(oldFirst);
            if (!incumbent.lookaheadLoss) {
                // No nonnegative local SSE can beat this exact trajectory.
                walkTo(working, co, std::min(input.samples, start + 40), cursor, prefix);
                continue;
            }
            auto immediate = incumbent, delayed = incumbent;
            legalPulses(input.profile, [&](Pulse pulse) {
                if (pulse == oldFirst) return;
                auto choice = firstTrial(pulse);
                if (choice.prefixLoss < immediate.prefixLoss) immediate = choice;
                if (choice.lookaheadLoss < delayed.lookaheadLoss) delayed = choice;
            });
            std::vector<FirstChoice> firstChoices{incumbent};
            for (const auto& choice : {immediate, delayed}) {
                bool duplicate = false;
                for (const auto& old : firstChoices) duplicate |= choice.pulse == old.pulse;
                if (!duplicate) firstChoices.push_back(choice);
            }

            uint64_t bestLoss = incumbent.lookaheadLoss;
            auto bestFirst = oldFirst, bestSecond = oldSecond;
            if (secondStart < input.samples) {
                for (const auto& first : firstChoices) {
                    working.pulses[firstIndex] = first.pulse;
                    auto secondTrial = [&](Pulse second) {
                        working.pulses[firstIndex + 1] = second;
                        auto state = first.after;
                        auto out = advance(working, co, secondStart, end, state);
                        uint64_t loss = first.prefixLoss + sse(context.reference, out, secondStart);
                        ++result.localEvaluations;
                        if (loss < bestLoss) {
                            bestLoss = loss; bestFirst = first.pulse; bestSecond = second;
                        }
                    };
                    secondTrial(oldSecond);
                    legalPulses(input.profile, [&](Pulse pulse) {
                        if (pulse != oldSecond) secondTrial(pulse);
                    });
                }
            } else if (delayed.lookaheadLoss < bestLoss) {
                bestLoss = delayed.lookaheadLoss; bestFirst = delayed.pulse;
            }
            working.pulses[firstIndex] = bestFirst;
            working.pulses[firstIndex + 1] = bestSecond;
            if (bestLoss < incumbent.lookaheadLoss)
                patches.push_back({start, bestFirst, bestSecond, incumbent.lookaheadLoss - bestLoss});
            walkTo(working, co, std::min(input.samples, start + 40), cursor, prefix);
        }
    }
    if (patches.empty()) return result;

    // The whole pass may trade local benefits against distant pitch feedback.
    // A fixed backoff set salvages useful subsets without relaxing any floor.
    std::sort(patches.begin(), patches.end(), [](const Patch& a, const Patch& b) {
        return a.benefit != b.benefit ? a.benefit > b.benefit : a.start < b.start;
    });
    std::vector<int> counts;
    const int n = patches.size();
    for (int count : {n, (n + 1) / 2, (n + 3) / 4, 1})
        if (std::find(counts.begin(), counts.end(), count) == counts.end()) counts.push_back(count);
    auto selectedMeasurement = baseline;
    uint64_t rawLoss = baseline.quality.error[0];
    for (int count : counts) {
        Stream candidate = input;
        for (int i = 0; i < count; ++i) {
            const auto& patch = patches[i];
            candidate.pulses[patch.start / 20] = patch.first;
            candidate.pulses[patch.start / 20 + 1] = patch.second;
        }
        // All pulse packets have fixed width. Checking the serialized result
        // also protects the zero-gain/tail accounting used by V9 callers.
        if (cost(candidate) != bytes) continue;
        auto pcm = render(candidate);
        auto measured = context.measure(pcm);
        ++result.fullEvaluations;
        if (measured.quality.error[0] < rawLoss) {
            rawLoss = measured.quality.error[0]; result.raw = candidate;
        }
        if (!completeGate(measured, baseline)) continue;
        result.alternatives.push_back(candidate);
        if (measured.score < selectedMeasurement.score
            || (measured.score == selectedMeasurement.score
                && measured.quality.error[0] < selectedMeasurement.quality.error[0])) {
            result.selected = candidate; selectedMeasurement = measured; ++result.accepted;
        }
    }
    return result;
}
}
