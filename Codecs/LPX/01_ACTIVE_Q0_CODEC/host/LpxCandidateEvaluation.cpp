#include "LpxCandidateEvaluation.h"
#include "LpxAdaptiveController.h"
#include <algorithm>

namespace lpx {
CandidateEvaluation::CandidateEvaluation(const Pcm& source,int sampleRate,bool isSpeech)
    : reference(source),rate(sampleRate),speech(isSpeech),quality(source,isSpeech,sampleRate),spectrum(source,sampleRate) {}
bool CandidateEvaluation::matches(const Pcm& source,int sampleRate,bool isSpeech) const {
    return &reference==&source && rate==sampleRate && speech==isSpeech;
}
bool CandidateEvaluation::measure(const Stream& stream,const std::vector<uint8_t>& packed,
    Measurement& measured,FullBandMeasurement& spectral,Pcm* supplied) {
    if(stream.samples!=int(reference.size()) || stream.rate!=rate || packed.empty())return false;
    // Equal packets alone are insufficient for continuation: rendering also
    // depends on the preceding LPC spectrum and the complete synthesis state.
    const Spectrum previous=stream.continuation?stream.previousSpectrum:Spectrum{};
    for(const auto& entry:cache) {
        const auto& a=entry.initial;const auto& b=stream.initial;
        if(entry.packed==packed && entry.continuation==stream.continuation && entry.previousSpectrum==previous && a.dd==b.dd && a.cc==b.cc
            && std::equal(a.h,a.h+10,b.h) && std::equal(a.ring,a.ring+256,b.ring)) {
            measured=entry.measured;spectral=entry.spectral;++hitCount;return true;
        }
    }
    Pcm generated;auto& pcm=supplied?*supplied:generated;
    if(pcm.empty())pcm=render(stream);
    if(!verifyStream(stream,pcm))return false;
    measured=quality.measure(pcm);spectral=spectrum.measure(pcm);
    // At most eight scalar summaries and 64 KiB of exact packet keys. Never
    // retain candidate PCM, and bypass the cache for larger individual files.
    if(packed.size()<=65536) {
        while(!cache.empty() && (cache.size()>=8 || retainedBytes+packed.size()>65536)) {
            retainedBytes-=cache.front().packed.size();cache.pop_front();
        }
        Entry entry;entry.packed=packed;entry.initial=stream.initial;entry.previousSpectrum=previous;entry.continuation=stream.continuation;
        entry.measured=measured;entry.spectral=spectral;cache.push_back(std::move(entry));retainedBytes+=packed.size();
    }
    return true;
}
}
