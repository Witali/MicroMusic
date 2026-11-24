#pragma once
#include "LpxQuality.h"
#include "LpxFullBand.h"
#include <deque>

namespace lpx {
// Actual-rate evaluation belongs to one immutable reference/session. Legacy
// 8 kHz controller measurements deliberately remain separate.
class CandidateEvaluation {
    struct Entry {
        std::vector<uint8_t> packed;
        SynthesisState initial;
        Spectrum previousSpectrum;
        bool continuation=false;
        Measurement measured;
        FullBandMeasurement spectral;
    };
    const Pcm& reference;
    int rate;
    bool speech;
    std::deque<Entry> cache;
    size_t retainedBytes=0, hitCount=0;
public:
    QualityContext quality;
    FullBandContext spectrum;
    CandidateEvaluation(const Pcm& reference,int rate,bool speech);
    bool matches(const Pcm& source,int sampleRate,bool isSpeech) const;
    bool measure(const Stream& stream,const std::vector<uint8_t>& packed,
                 Measurement& measured,FullBandMeasurement& spectral,Pcm* pcm=nullptr);
    size_t hits() const { return hitCount; }
    size_t cachedBytes() const { return retainedBytes; }
};
}
