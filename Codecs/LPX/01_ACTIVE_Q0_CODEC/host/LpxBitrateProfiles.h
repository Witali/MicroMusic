#pragma once
#include "LpxAdaptive.h"

namespace lpx {
struct BitrateReport {
    int candidates = 0, selected = 0, error = 0;
    uint64_t parameterTrials = 0, pulseTrials = 0;
};
using ThreeKCandidateVisitor = void (*)(const Stream&, const Pcm&, void*);
// Conservative bound for the existing fixed search: three seeds and at most
// four plan variants per pre setting, plus an optional incumbent. The <=6
// zero-gain fallback visits occur only when no normal candidate was visited.
constexpr int kThreeKMaxCandidateVisits = 16;
// The caller owns whole-input level planning and reserves the seed workspace.
// maxBytes counts the final ordinary/Long V9 header and complete payload.
// A successful result is ordinary P4 syntax; no decoder extension is needed.
// A visitor observes each cap-compatible complete candidate after native
// decoder verification, before legacy measurements/winner filters. PCM is the
// already rendered candidate, not a changed reference. Visits retain existing
// order and duplicates, including an optional incumbent. References are valid
// only during the callback; it must not mutate/re-enter the seed workspace or
// throw. Valid visits may precede a later overall error. A null visitor adds
// no rendering, copies, measurements or allocations and keeps legacy behavior.
Stream encodeThreeK(const Pcm& reference, int maxBytes, BitrateReport& report,
                    double bandwidth = .97, const Stream* incumbent = nullptr,
                    ThreeKCandidateVisitor visitor = nullptr, void* visitorContext = nullptr);
}
