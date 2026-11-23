#pragma once
#include "LpxAdaptive.h"

namespace lpx {
struct BitrateReport {
    int candidates = 0, selected = 0, error = 0;
    uint64_t parameterTrials = 0, pulseTrials = 0;
};
// The caller owns whole-input level planning and reserves the seed workspace.
// maxBytes counts the final ordinary/Long V9 header and complete payload.
// A successful result is ordinary P4 syntax; no decoder extension is needed.
Stream encodeThreeK(const Pcm& reference, int maxBytes, BitrateReport& report,
                    double bandwidth = .97, const Stream* incumbent = nullptr,
                    const Stream* prefix = nullptr);
}
