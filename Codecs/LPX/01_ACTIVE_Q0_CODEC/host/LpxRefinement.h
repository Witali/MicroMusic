#pragma once
#include "LpxQuality.h"

namespace lpx {
struct RefinementResult {
    Stream selected, raw;
    std::vector<Stream> alternatives;
    int localEvaluations = 0, fullEvaluations = 0, accepted = 0;
};
RefinementResult refineHeader(const Stream& stream,const QualityContext& context);
RefinementResult enhanceExtras(const Stream& stream,const QualityContext& context,int cap);
RefinementResult refineLpc(const Stream& stream,const QualityContext& context,int cap);
// Optional extension beyond the Python-parity operators. It keeps the input
// candidate and evaluates the complete continuous output before acceptance.
RefinementResult refinePitchGain(const Stream& stream,const QualityContext& context,int cap);
}
