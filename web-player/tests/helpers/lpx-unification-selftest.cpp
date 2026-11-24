#include "LpxCandidateEvaluation.h"
#include "LpxEncoder.h"
#include "LpxEncoderContext.h"
#include "LpxAdaptive.h"
#include <cmath>
#include <algorithm>
#include <cstring>

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
extern "C" int seed_context_selftest() {
    using namespace lpx;
    SeedEncoder a,b;
    Pcm x(641),y(4097);
    for(size_t i=0;i<x.size();++i)x[i]=int(5000*std::sin(i*.17));
    for(size_t i=0;i<y.size();++i)y[i]=int(7000*std::sin(i*.23));
    auto begin=[](SeedEncoder& encoder,const Pcm& pcm,int profile) {
        if(!encoder.reserve(pcm.size()))return -1;
        std::copy(pcm.begin(),pcm.end(),encoder.source);
        return encoder.begin(pcm.size(),profile,8000);
    };
    auto finish=[](SeedEncoder& encoder) {
        const int size=encoder.finish();
        return size>0?std::vector<uint8_t>(encoder.packed,encoder.packed+size):std::vector<uint8_t>{};
    };
    int n=begin(a,x,4);if(n<1)return 101;
    for(int i=0;i<n;++i)if(a.step()<0)return 102;
    const auto expectedA=finish(a);
    n=begin(b,y,6);if(n<1)return 103;
    for(int i=0;i<n;++i)if(b.step()<0)return 104;
    const auto expectedB=finish(b);
    if(expectedA.empty() || expectedB.empty())return 105;
    const int na=begin(a,x,4);if(na<1 || a.step()<0)return 106;
    const auto inputA=a.source;
    b.release();const int nb=begin(b,y,6);
    if(nb<1 || a.source!=inputA || a.source==b.source)return 107;
    for(int i=0;i<std::max(na,nb);++i) {
        if(i>0 && i<na && a.step()<0)return 108;
        if(i<nb && b.step()<0)return 109;
    }
    if(finish(a)!=expectedA || finish(b)!=expectedB)return 110;
    // The owning Stream API can also use an explicit workspace without
    // changing its existing default-context entry point.
    auto local=fitSeed(x,4,8000,13926,false,.97,nullptr,&a);
    if(!enc_reserve(x.size()))return 111;
    auto legacy=fitSeed(x,4,8000,13926,false);
    if(packV9(local)!=packV9(legacy))return 112;
    a.release();if(a.source || a.reservedSamples)return 113;
    return 0;
}
extern "C" int spectrum_safety_selftest() {
    using namespace lpx;
    const double tau=6.28318530717958647692;
    Pcm edge(512),quantized(512),centered(512),unrelated(512),inverted(512),aboveFloor(512),aboveFloorUnrelated(512);
    double rawPower=0,weightedPower=0,windowPower=0,aboveFloorPower=0;
    for(int i=0;i<512;++i) {
        // A short onset is loud in raw PCM but nearly absent under the Hann
        // window. Quiet periodic quantization error dominates that spectrum.
        if(i<32)edge[i]=int(1000*std::sin(tau*3*i/32));
        quantized[i]=edge[i]+(i%4<2?12:-12);
        const double w=.5-.5*std::cos(tau*i/511);
        rawPower+=double(edge[i])*edge[i];
        weightedPower+=double(edge[i])*edge[i]*w*w;windowPower+=w*w;
        centered[i]=int(3000*std::sin(tau*3*i/32));
        unrelated[i]=int(3000*std::sin(tau*10*i/32));
        inverted[i]=-centered[i];
        aboveFloor[i]=int(128*std::sin(tau*3*i/32));
        aboveFloorUnrelated[i]=int(128*std::sin(tau*10*i/32));
        aboveFloorPower+=double(aboveFloor[i])*aboveFloor[i]*w*w;
    }
    // Establish the physical fixture on both sides of the eligibility floor.
    if(rawPower<=512.*64*64 || weightedPower>=windowPower*64*64)return 201;
    if(!safeSynthesisSpectrum(edge,quantized))return 202;
    if(!safeSynthesisSpectrum(centered,centered))return 203;
    if(!safeSynthesisSpectrum(centered,inverted))return 204;
    if(safeSynthesisSpectrum(centered,unrelated))return 205;
    // Above 64 Hann RMS must remain eligible: a raw 512-sample denominator
    // would incorrectly skip this still-significant centered source.
    if(aboveFloorPower<=windowPower*64*64 || aboveFloorPower>=512.*64*64)return 206;
    if(safeSynthesisSpectrum(aboveFloor,aboveFloorUnrelated))return 207;
    return 0;
}
#if !defined(__wasm__)
int main() {
    int error=unification_selftest();if(error)return error;
    error=seed_context_selftest();return error?error:spectrum_safety_selftest();
}
#endif
