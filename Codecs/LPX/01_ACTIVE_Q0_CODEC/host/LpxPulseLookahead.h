#pragma once
#include "LpxRefinement.h"

namespace lpx {
// Fixed-width pulse-only proposals: spectrum, parameters, filters and extras
// stay unchanged. cap uses v5 accounting by default, or final V9 bytes when
// finalV9Budget is true. The protected complete input is always retained.
RefinementResult refinePulseLookahead(const Stream& stream,
    const QualityContext& context, int cap, bool finalV9Budget = false);
}
