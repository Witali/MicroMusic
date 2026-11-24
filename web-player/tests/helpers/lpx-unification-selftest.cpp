#include "LpxCandidateEvaluation.h"
#include "LpxEncoder.h"
#include <cmath>

extern "C" int unification_selftest() {
    using namespace lpx;
    Pcm reference(641);for(int i=0;i<641;++i)reference[i]=int(5000*std::sin(i*.17));
    if(!enc_reserve(reference.size()))return 1;
    Stream stream=fitSeed(reference,4,8000,13926,false);
    const auto packed=packV9(stream);
    CandidateEvaluation evaluation(reference,8000,true);
    Measurement a,b;FullBandMeasurement x,y;Pcm pcm;
    if(!evaluation.measure(stream,packed,a,x,&pcm) || pcm.size()!=reference.size())return 2;
    pcm.clear();
    if(!evaluation.measure(stream,packed,b,y,&pcm) || !pcm.empty() || evaluation.hits()!=1)return 3;
    for(int p=0;p<2;++p)if(a.quality.error[p]!=b.quality.error[p]
        || x.balancedError[p]!=y.balancedError[p] || x.balancedTemporalError[p]!=y.balancedTemporalError[p])return 4;
    // Identical wire bytes with different continuation state must miss.
    Stream continued=stream;continued.continuation=true;continued.previousSpectrum=stream.spectra[0];
    for(int variant=0;variant<5;++variant) {
        if(variant==1)continued.initial.dd=123;
        if(variant==2)continued.initial.cc=321;
        if(variant==3)continued.initial.ring[255]=4;
        if(variant==4)continued.previousSpectrum[0]++;
        if(!evaluation.measure(continued,packed,b,y) || evaluation.hits()!=1)return 5;
    }
    for(int i=0;i<12;++i) {
        stream.pre=1000+i*100;
        if(!evaluation.measure(stream,packV9(stream),b,y) || evaluation.cachedBytes()>65536)return 6;
    }
    const auto copy=reference;
    if(evaluation.matches(copy,8000,true) || evaluation.matches(reference,12000,true)
        || evaluation.matches(reference,8000,false))return 7;
    return 0;
}
#if !defined(__wasm__)
int main() { return unification_selftest(); }
#endif
